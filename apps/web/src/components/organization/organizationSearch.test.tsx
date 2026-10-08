import { organizationMatchesSearch } from "@/components/organization/organizationSearch";

it.each(["load test 00092", "00092 load", "  load   test 00092 "])(
  "matches separated words in %s",
  (query) => {
    expect(
      organizationMatchesSearch({ name: "Load Test Unit 00092" }, query, "tr")
    ).toBe(true);
    expect(
      organizationMatchesSearch({ name: "Load Test Unit 00093" }, query, "tr")
    ).toBe(false);
  }
);

it("keeps literal characters and empty queries from matching everything", () => {
  expect(
    organizationMatchesSearch({ name: "Load Test Unit 00092" }, "%", "en")
  ).toBe(false);
  expect(
    organizationMatchesSearch({ name: "Load Test Unit 00092" }, "  ", "en")
  ).toBe(false);
});
