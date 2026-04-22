/**
 * Utilities for converting browser File objects into inline base64 content
 * that the agent-service backend can process directly inside the message payload.
 *
 * This mirrors the legacy open-agent-platform pattern: no separate upload
 * endpoint is called — files are base64-encoded and sent inline with the
 * chat message.
 */

import { ChatFileType, FileDescriptor } from "@/app/app/interfaces";
import { UserFileStatus } from "@/app/app/projects/projectsService";

// ---------------------------------------------------------------------------
// Accepted MIME types (mirrors FileService.py ACCEPTED_MIMES)
// ---------------------------------------------------------------------------

export const ACCEPTED_IMAGE_MIMES = new Set([
  "image/jpeg",
  "image/jpg",
  "image/pjpeg",
  "image/jfif",
  "image/png",
  "image/gif",
  "image/webp",
]);

export const ACCEPTED_DOCUMENT_MIMES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.ms-powerpoint",
]);

export const ACCEPTED_CSV_MIMES = new Set([
  "text/csv",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
]);

export const ACCEPTED_PLAIN_TEXT_MIMES = new Set([
  "text/plain",
  "text/markdown",
]);

export const ALL_ACCEPTED_MIMES = new Set([
  ...Array.from(ACCEPTED_IMAGE_MIMES),
  ...Array.from(ACCEPTED_DOCUMENT_MIMES),
  ...Array.from(ACCEPTED_CSV_MIMES),
  ...Array.from(ACCEPTED_PLAIN_TEXT_MIMES),
]);

/** Human-readable file accept string for <input type="file"> */
export const CHAT_FILE_INPUT_ACCEPT = [
  // Images (including rare JPEG variants)
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
  ".jfif",
  ".jpe",
  ".pjp",
  ".pjpeg",
  // Documents
  "application/pdf",
  ".docx",
  ".doc",
  ".pptx",
  ".ppt",
  // Spreadsheets / tabular
  "text/csv",
  ".csv",
  ".xlsx",
  ".xls",
  // Plain text
  "text/plain",
  ".txt",
  ".md",
].join(",");

// ---------------------------------------------------------------------------
// MIME → ChatFileType
// ---------------------------------------------------------------------------

export function mimeTypeToChatFileType(mime: string): ChatFileType {
  const m = (mime.toLowerCase().split(";")[0] ?? "").trim();
  if (ACCEPTED_IMAGE_MIMES.has(m)) return ChatFileType.IMAGE;
  if (ACCEPTED_CSV_MIMES.has(m)) return ChatFileType.CSV;
  if (ACCEPTED_PLAIN_TEXT_MIMES.has(m)) return ChatFileType.PLAIN_TEXT;
  return ChatFileType.DOCUMENT;
}

// ---------------------------------------------------------------------------
// Core conversion helpers
// ---------------------------------------------------------------------------

/** Generate a UUID that works in both secure (HTTPS) and non-secure contexts. */
export function generateUUID(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for HTTP (non-secure) contexts
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = Math.trunc(Math.random() * 16);
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** Read a File as a base64 string (without the data:...;base64, prefix). */
export async function fileToBase64(file: File): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1] ?? "");
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/**
 * Convert a File into a FileDescriptor with inline base64 data.
 *
 * The returned descriptor can be included directly in the `file_descriptors`
 * array of the send-chat-message payload. The backend decodes `data` and
 * extracts content using LangChain loaders — no separate upload is needed.
 */
export async function fileToFileDescriptor(file: File): Promise<FileDescriptor> {
  const mime = file.type || "application/octet-stream";
  const chatFileType = mimeTypeToChatFileType(mime);
  const fileId = generateUUID();
  const data = await fileToBase64(file);

  return {
    id: fileId,
    type: chatFileType,
    name: file.name,
    mime_type: mime,
    data,
  };
}

/**
 * Convert a File into a ProjectFile-compatible object for the
 * currentMessageFiles state (optimistic UI).  Status is set to COMPLETED
 * immediately because no server upload is required.
 */
export async function fileToProjectFile(file: File) {
  const mime = file.type || "application/octet-stream";
  const chatFileType = mimeTypeToChatFileType(mime);
  const fileId = generateUUID();
  const data = await fileToBase64(file);

  return {
    id: fileId,
    file_id: fileId,
    name: file.name,
    project_id: null,
    user_id: null,
    created_at: new Date().toISOString(),
    status: UserFileStatus.COMPLETED,
    file_type: mime,
    last_accessed_at: new Date().toISOString(),
    chat_file_type: chatFileType,
    token_count: null,
    chunk_count: null,
    temp_id: null,
    // Extended — carries the inline base64 for later FileDescriptor construction
    _inline_data: data,
    _mime_type: mime,
  };
}
