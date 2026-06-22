import { redirect } from "next/navigation";
import { getAuthTypeMetadataSS } from "@/lib/userSS";
import { getLoginPath } from "@/lib/auth/loginRoute";

export default async function Page() {
  const authTypeMetadata = await getAuthTypeMetadataSS();
  redirect(getLoginPath(authTypeMetadata));
}
