import { authenticatedFetch, RedirectError } from "@/lib/fetcher";

const userMutationFetcher = async (
  url: string,
  { arg }: { arg: Record<string, unknown> & { method?: string } }
) => {
  const { method = "PATCH", ...body } = arg;
  try {
    const res = await authenticatedFetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (res.ok) return res.json();

    const errorDetail = (await res.json()).detail;
    throw Error(errorDetail);
  } catch (error) {
    // Re-throw RedirectError so it propagates properly and doesn't get caught by SWR
    if (error instanceof RedirectError) {
      throw error;
    }
    throw error;
  }
};

export default userMutationFetcher;
