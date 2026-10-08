import { VIRTUAL_H, VIRTUAL_W } from "../constants";
import { makeEnv } from "../env";
import { kablo } from "./kablo";

/** Widest reach of the Wi-Fi rings to the left of the modem's centre. */
const WIFI_LEFT_REACH = 150;
/** Widest reach of the TV cluster to the right of the set-top box column. */
const TV_RIGHT_REACH = 120;

function kabloAt(width: number, columnWidth: number) {
  const env = makeEnv({
    company: "kablo",
    dark: false,
    width,
    height: VIRTUAL_H,
    anchorY: 1,
    columnWidth,
  });
  return { env, st: kablo.init(env) };
}

describe("kablo layout beside a wide message column", () => {
  it.each([
    [VIRTUAL_W, 840],
    [VIRTUAL_W, 5000],
    [1818, 800],
  ])(
    "keeps the modem and its Wi-Fi rings inside the frame (width %d, column %d)",
    (width, column) => {
      const { st } = kabloAt(width, column);

      expect(st.M.x + st.M.w / 2 - WIFI_LEFT_REACH).toBeGreaterThanOrEqual(0);
    }
  );

  it.each([
    [VIRTUAL_W, 840],
    [VIRTUAL_W, 5000],
    [1818, 800],
  ])(
    "keeps the TV cluster inside the frame (width %d, column %d)",
    (width, column) => {
      const { env, st } = kabloAt(width, column);

      expect(st.tv.x + st.tv.w).toBeLessThanOrEqual(env.w);
      expect(st.con.x + st.con.w + TV_RIGHT_REACH - 106).toBeLessThanOrEqual(
        env.w
      );
    }
  );
});
