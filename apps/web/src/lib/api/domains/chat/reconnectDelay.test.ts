import { reconnectDelayMs } from "./resumableChatStream";

describe("reconnectDelayMs", () => {
  it("spreads each attempt over the upper half of its exponential step", () => {
    // After a deploy or a network blip every tab reconnects at once; a wide
    // random spread keeps them from hitting the server in the same instant.
    expect(reconnectDelayMs(1, () => 0)).toBe(250);
    expect(reconnectDelayMs(1, () => 0.999)).toBeCloseTo(500, -1);
    expect(reconnectDelayMs(3, () => 0)).toBe(1000);
    expect(reconnectDelayMs(3, () => 0.999)).toBeCloseTo(2000, -1);
  });

  it("caps the step at 10 seconds", () => {
    expect(reconnectDelayMs(20, () => 0)).toBe(5000);
    expect(reconnectDelayMs(20, () => 0.999)).toBeLessThanOrEqual(10_000);
  });
});
