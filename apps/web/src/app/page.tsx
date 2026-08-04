import { redirect } from "next/navigation";
import { getAuthTypeMetadataSS, getCurrentUserSS } from "@/lib/userSS";
import { getLoginPath } from "@/lib/auth/loginRoute";

export default async function Page() {
  const [authTypeMetadata, currentUser] = await Promise.all([
    getAuthTypeMetadataSS(),
    getCurrentUserSS(),
  ]);

  if (currentUser?.is_active && !currentUser.is_anonymous_user) {
    if (authTypeMetadata.requiresVerification && !currentUser.is_verified) {
      redirect("/auth/waiting-on-verification");
    }

    redirect("/app");
  }

  redirect(getLoginPath(authTypeMetadata));
}
