import { forwardSetCookies } from "./forwardSetCookies";

const SESSION = "session=abc; Path=/; HttpOnly";
const REFRESH = "refresh=xyz; Path=/auth; HttpOnly";

describe("forwardSetCookies", () => {
  it("keeps every cookie separate instead of folding them into one", () => {
    const from = new Headers();
    from.append("set-cookie", SESSION);
    from.append("set-cookie", REFRESH);
    const to = new Headers();

    forwardSetCookies(from, to);

    expect(to.getSetCookie()).toEqual([SESSION, REFRESH]);
  });

  it("is a no-op when the backend set no cookies", () => {
    const to = new Headers();

    forwardSetCookies(new Headers(), to);

    expect(to.getSetCookie()).toEqual([]);
  });

  it("does not disturb cookies the caller already set", () => {
    const from = new Headers();
    from.append("set-cookie", REFRESH);
    const to = new Headers();
    to.append("set-cookie", SESSION);

    forwardSetCookies(from, to);

    expect(to.getSetCookie()).toEqual([SESSION, REFRESH]);
  });
});
