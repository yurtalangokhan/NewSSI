import { filterByText } from "@/lib/text/textFilter";

const items = [{ name: "Hukuk & Sözleşmeler" }, { name: "Kurumsal Graph" }];
const nameOf = (item: { name: string }) => item.name;

describe("filterByText", () => {
  it("returns every item for a blank query", () => {
    expect(filterByText(items, "  ", nameOf)).toBe(items);
  });

  it("matches a substring, ignoring case and surrounding space", () => {
    expect(filterByText(items, " GRAPH ", nameOf)).toEqual([items[1]]);
  });

  it("matches accented letters case-insensitively", () => {
    expect(filterByText(items, "SÖZLEŞ", nameOf)).toEqual([items[0]]);
  });

  it("returns nothing when no item matches", () => {
    expect(filterByText(items, "zzz", nameOf)).toEqual([]);
  });
});
