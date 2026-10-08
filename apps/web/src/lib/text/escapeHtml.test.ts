import { escapeHtml } from "@/lib/text/escapeHtml";

describe("escapeHtml", () => {
  it("escapes markup and quote characters", () => {
    expect(escapeHtml(`<img src=x onerror="a('b')">&`)).toBe(
      "&lt;img src=x onerror=&quot;a(&#39;b&#39;)&quot;&gt;&amp;"
    );
  });

  it("escapes the ampersand first so entities are not double-escaped", () => {
    expect(escapeHtml("a & <b>")).toBe("a &amp; &lt;b&gt;");
  });

  it("leaves plain and non-ASCII text alone", () => {
    expect(escapeHtml("Veri Saklama Politikası")).toBe(
      "Veri Saklama Politikası"
    );
  });
});
