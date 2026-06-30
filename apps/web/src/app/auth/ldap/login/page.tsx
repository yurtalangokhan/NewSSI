import { redirect } from "next/navigation";
import type { Route } from "next";
import { getAuthTypeMetadataSS } from "@/lib/userSS";
import { buildLoginPath } from "@/lib/auth/loginRoute";

export default async function Page() {
  let loginPath = "/auth/login";
  try {
    loginPath = buildLoginPath(await getAuthTypeMetadataSS());
  } catch (e) {
    console.log(`Fetch failed for LDAP login page - ${e}`);
  }

  return redirect(loginPath as Route);
}
