import { FileDescriptor } from "../interfaces";
import { ProjectFile } from "../projects/projectsService";

export function projectsFileToFileDescriptor(
  file: ProjectFile
): FileDescriptor {
  // _inline_data / _mime_type are set by uploadChatFiles (inline base64 flow).
  // Forward them so the backend can receive the file contents in the payload.
  const extended = file as ProjectFile & {
    _inline_data?: string | null;
    _mime_type?: string | null;
  };
  return {
    id: file.file_id,
    type: file.chat_file_type,
    name: file.name,
    user_file_id: file.id,
    data: extended._inline_data ?? null,
    mime_type: extended._mime_type ?? null,
  };
}

export function projectFilesToFileDescriptors(
  files: ProjectFile[]
): FileDescriptor[] {
  return files.map(projectsFileToFileDescriptor);
}
