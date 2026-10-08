import { highlightSegments } from "@/lib/text/highlight";

describe("highlightSegments", () => {
  it("marks query words case-insensitively, Turkish casing included", () => {
    const segments = highlightSegments(
      "İzin devri için birim yöneticisinin onayı gerekir.",
      "izin DEVRİ onay"
    );

    expect(segments.filter((s) => s.match).map((s) => s.text)).toEqual([
      "İzin",
      "devri",
      "onay",
    ]);
    expect(segments.map((s) => s.text).join("")).toBe(
      "İzin devri için birim yöneticisinin onayı gerekir."
    );
  });

  it("ignores very short words and regex characters in the query", () => {
    const segments = highlightSegments("a (b) c+d", "a ( c+");
    expect(segments.every((s) => !s.match)).toBe(true);
  });

  it("returns the text unchanged when there is no query", () => {
    expect(highlightSegments("metin", "")).toEqual([
      { text: "metin", match: false },
    ]);
  });
});
