import { parseApiErrorResponse } from "@/lib/api/errors";

export const getErrorMsg = async (response: Response) => {
  if (response.ok) {
    return null;
  }
  const parsedError = await parseApiErrorResponse(response);
  return parsedError.userMessage || "Unknown error";
};
