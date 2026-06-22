import { User } from "@/lib/types";
import { getCurrentUserSS } from "@/lib/userSS";
import { redirect } from "next/navigation";
import Link from "next/link";
import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import LdapLoginForm from "./LdapLoginForm";

export default async function Page() {
  let currentUser: User | null = null;
  try {
    currentUser = await getCurrentUserSS();
  } catch (e) {
    console.log(`Fetch failed for LDAP login page - ${e}`);
  }

  if (currentUser && currentUser.is_active && !currentUser.is_anonymous_user) {
    return redirect("/app");
  }

  const footerContent = (
    <Link
      href="/auth/login"
      className="text-white mainUiAction underline transition-colors duration-200"
    >
      Back to Login
    </Link>
  );

  return (
    <div className="flex flex-col">
      <AuthFlowContainer authState="login" footerContent={footerContent}>
        <LdapLoginForm />
      </AuthFlowContainer>
    </div>
  );
}
