import { VIRTUAL_H, VIRTUAL_W } from "./constants";
import { makeEnv } from "./env";

const base = {
  company: "bilisim",
  dark: false,
  width: VIRTUAL_W,
  height: VIRTUAL_H,
  anchorY: 0.5,
  columnWidth: 720,
} as const;

describe("makeEnv", () => {
  it("centers a message column inside the virtual frame", () => {
    const env = makeEnv(base);

    expect(env.cx).toBe(VIRTUAL_W / 2);
    expect(env.colW).toBe(720);
    expect(env.colL).toBe(env.cx - 360);
    expect(env.colR).toBe(env.cx + 360);
  });

  it("carries the company and color mode it was built for", () => {
    const env = makeEnv({ ...base, company: "kablo", dark: true });

    expect(env.company).toBe("kablo");
    expect(env.dark).toBe(true);
  });

  it("stretches the frame and its centered column with a wider virtual width", () => {
    const env = makeEnv({ ...base, company: "uydu", width: 2000 });

    expect(env.w).toBe(2000);
    expect(env.cx).toBe(1000);
    expect(env.colR).toBeLessThan(2000);
  });

  it("never lets the message column take more than 62% of the frame, so the side compositions still fit beside it", () => {
    const env = makeEnv({ ...base, columnWidth: 5000 });

    expect(env.colW).toBeCloseTo(VIRTUAL_W * 0.62, 5);
  });

  describe("vertical anchoring in a taller frame", () => {
    const tall = { ...base, height: 1500 };

    it("centers the authored scene by default", () => {
      const env = makeEnv({ ...tall, anchorY: 0.5 });

      expect(env.h).toBe(1500);
      expect(env.top).toBe(-300);
      expect(env.bottom).toBe(1200);
    });

    it("sits the scene on the frame's bottom edge when anchored to the bottom", () => {
      const env = makeEnv({ ...tall, anchorY: 1 });

      expect(env.top).toBe(-600);
      expect(env.bottom).toBe(VIRTUAL_H);
    });

    it("sits the scene on the frame's top edge when anchored to the top", () => {
      const env = makeEnv({ ...tall, anchorY: 0 });

      expect(env.top).toBe(0);
      expect(env.bottom).toBe(1500);
    });
  });

  it("starts the frame at the scene's own top when it is not taller than the scene", () => {
    const env = makeEnv(base);

    expect(env.top).toBe(0);
    expect(env.bottom).toBe(VIRTUAL_H);
  });
});
