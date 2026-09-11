import {
  hashName,
  deriveMedallion,
  TRANSPONDER_PALETTE,
} from "@/refresh-components/avatars/medallion";

describe("hashName", () => {
  it("is deterministic", () => {
    expect(hashName("Kurumsal Asistan")).toBe(hashName("Kurumsal Asistan"));
  });

  it("returns an unsigned 32-bit integer", () => {
    const h = hashName("Fatura Onay Akışı");
    expect(Number.isInteger(h)).toBe(true);
    expect(h).toBeGreaterThanOrEqual(0);
    expect(h).toBeLessThanOrEqual(0xffffffff);
  });

  it("locks known values so the palette mapping can't silently drift", () => {
    expect(hashName("Kurumsal Asistan")).toBe(1605705534);
    expect(hashName("Hukuk Danışmanı")).toBe(2065171435);
  });
});

describe("deriveMedallion", () => {
  it("maps known names to a stable hue / count / primary", () => {
    expect(deriveMedallion("Kurumsal Asistan", "agent")).toMatchObject({
      accent: "#009BDA",
      count: 3,
      primaryIndex: 0,
    });
    expect(deriveMedallion("Fatura Onay Akışı", "flow")).toMatchObject({
      accent: "#8A49C9",
      count: 5,
      primaryIndex: 4,
    });
  });

  it("always picks a palette hue and 3–5 satellites", () => {
    for (const name of [
      "a",
      "bb",
      "ccc",
      "Destek",
      "Rapor",
      "İK",
      "Envanter 7",
    ]) {
      const g = deriveMedallion(name, "agent");
      expect(TRANSPONDER_PALETTE).toContain(g.accent);
      expect(g.count).toBeGreaterThanOrEqual(3);
      expect(g.count).toBeLessThanOrEqual(5);
      expect(g.points).toHaveLength(g.count);
      expect(g.primaryIndex).toBeGreaterThanOrEqual(0);
      expect(g.primaryIndex).toBeLessThan(g.count);
    }
  });

  it("falls back to a stable identity for a blank name", () => {
    expect(deriveMedallion("   ", "agent")).toEqual(
      deriveMedallion("Agent", "agent")
    );
  });

  it("keeps satellite centres on the orbit band of the 48-box", () => {
    const g = deriveMedallion("Kurumsal Asistan", "agent");
    for (const p of g.points) {
      const d = Math.hypot(p.x - 24, p.y - 24);
      expect(d).toBeGreaterThan(12);
      expect(d).toBeLessThan(16);
    }
  });

  describe("flow variant", () => {
    it("orders pathPoints by angle; they are a permutation of points", () => {
      const g = deriveMedallion("Fatura Onay Akışı", "flow");
      expect(g.pathPoints).toHaveLength(g.points.length);
      const key = (p: { x: number; y: number }) => `${p.x},${p.y}`;
      expect(g.pathPoints.map(key).sort()).toEqual(g.points.map(key).sort());
      const angles = g.pathPoints.map((p) => Math.atan2(p.y - 24, p.x - 24));
      expect(angles).toEqual([...angles].sort((a, b) => a - b));
    });

    it("produces an arrowhead path starting with a moveto", () => {
      expect(
        deriveMedallion("Fatura Onay Akışı", "flow").arrowD.startsWith("M")
      ).toBe(true);
    });
  });

  it("leaves flow-only fields empty for agents", () => {
    const g = deriveMedallion("Kurumsal Asistan", "agent");
    expect(g.pathPoints).toEqual([]);
    expect(g.arrowD).toBe("");
  });
});
