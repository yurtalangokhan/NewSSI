/**
 * The items whose text contains the query, ignoring case and surrounding
 * space. A blank query keeps every item (the same array, so callers can rely
 * on referential equality when nothing is filtered).
 */
export function filterByText<T>(
  items: readonly T[],
  query: string,
  textOf: (item: T) => string
): readonly T[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return items;
  return items.filter((item) =>
    textOf(item).toLocaleLowerCase().includes(needle)
  );
}
