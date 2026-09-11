import { chatFileDownloadUrl, resolveDownloadHref } from "./svc";

describe("chatFileDownloadUrl", () => {
  it("asks for the original bytes", () => {
    // The plain endpoint deliberately transcodes an XLSX to CSV so the table
    // preview can render it. Without download=1 the browser saves CSV text
    // under the .xlsx name and Excel rejects the file.
    expect(chatFileDownloadUrl("abc123")).toBe(
      "/api/chat/file/abc123?download=1"
    );
  });

  it("encodes the file id", () => {
    expect(chatFileDownloadUrl("a/b?c")).toBe(
      "/api/chat/file/a%2Fb%3Fc?download=1"
    );
  });
});

describe("resolveDownloadHref", () => {
  it("never hands back the preview blob for a stored file", () => {
    expect(resolveDownloadHref("abc123", "blob:http://x/preview", false)).toBe(
      "/api/chat/file/abc123?download=1"
    );
  });

  it("keeps the inline preview for a file that was never sent", () => {
    // An attachment chosen in the composer has no backend copy yet, so the
    // data:/blob: URL it is previewed from is the only thing to save.
    expect(
      resolveDownloadHref("local-1", "data:text/plain;base64,aGk=", true)
    ).toBe("data:text/plain;base64,aGk=");
  });
});
