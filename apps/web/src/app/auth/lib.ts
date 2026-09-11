import { idempotentFetch } from "@/lib/api/idempotency";

export async function requestEmailVerification(email: string) {
  return await idempotentFetch("/api/auth/request-verify-token", {
    headers: {
      "Content-Type": "application/json",
    },
    method: "POST",
    body: JSON.stringify({
      email: email,
    }),
  });
}
