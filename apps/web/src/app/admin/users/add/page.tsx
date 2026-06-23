"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_PATHS, ADMIN_ROUTE_CONFIG } from "@/lib/admin-routes";
import { toast } from "@/hooks/useToast";
import Button from "@/refresh-components/buttons/Button";
import CreateButton from "@/refresh-components/buttons/CreateButton";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import PasswordInputTypeIn from "@/refresh-components/inputs/PasswordInputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { authenticatedFetch } from "@/lib/fetcher";
import { useTranslation } from "react-i18next";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR from "swr";

const usersRoute = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.USERS]!;

export default function AddUserPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [role, setRole] = useState("enduser");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { data: roles } = useSWR<{ roles: { name: string }[] }>(
    "/api/user-service/roles/",
    errorHandlingFetcher
  );

  const disabled = useMemo(() => {
    return (
      isSubmitting ||
      !username.trim() ||
      !email.trim() ||
      !email.includes("@") ||
      !firstName.trim() ||
      !lastName.trim() ||
      !password.trim()
    );
  }, [email, firstName, isSubmitting, lastName, password, username]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (disabled) return;

    setIsSubmitting(true);
    try {
      const response = await authenticatedFetch("/api/user-service/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username.trim(),
          email: email.trim(),
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          role,
          password: password.trim() || undefined,
        }),
      });

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        const detail = errorBody?.detail || "Unknown error";
        throw new Error(detail);
      }

      toast.success(t("admin.users.createSuccess"));
      router.push("/admin/users");
      router.refresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      toast.error(t("admin.users.createError", { error: message }));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        title={t("admin.users.addUserPageTitle")}
        icon={usersRoute.icon}
        separator
      />
      <SettingsLayouts.Body>
        <form
          onSubmit={onSubmit}
          className="max-w-xl rounded-lg border border-border-subtle bg-background-100 p-6"
        >
          <div className="flex flex-col gap-4">
            <Text as="p" mainUiMuted>
              {t("admin.users.createDescription")}
            </Text>

            <div className="flex flex-col gap-1">
              <Text as="p" mainUiBody>
                {t("auth.usernameLabel", { defaultValue: "Username" })}
              </Text>
              <InputTypeIn
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="newuser"
                autoComplete="username"
                required
              />
            </div>

            <div className="flex flex-col gap-1">
              <Text as="p" mainUiBody>
                {t("auth.emailLabel", { defaultValue: "Email" })}
              </Text>
              <InputTypeIn
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                required
              />
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="flex flex-col gap-1">
                <Text as="p" mainUiBody>
                  {t("admin.users.editUserModal.firstNameLabel")}
                </Text>
                <InputTypeIn
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="John"
                  required
                />
              </div>

              <div className="flex flex-col gap-1">
                <Text as="p" mainUiBody>
                  {t("admin.users.editUserModal.lastNameLabel")}
                </Text>
                <InputTypeIn
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder="Doe"
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="flex flex-col gap-1">
                <Text as="p" mainUiBody>
                  {t("admin.users.roleHeader")}
                </Text>
                <InputSelect value={role} onValueChange={setRole}>
                  <InputSelect.Trigger />
                  <InputSelect.Content>
                    {roles?.roles?.map((r) => (
                      <InputSelect.Item key={r.name} value={r.name}>
                        {t(`admin.users.roles.${r.name}`)}
                      </InputSelect.Item>
                    ))}
                  </InputSelect.Content>
                </InputSelect>
              </div>

              <div className="flex flex-col gap-1">
                <Text as="p" mainUiBody>
                  {t("admin.users.createPasswordLabel")}
                </Text>
                <PasswordInputTypeIn
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t("admin.users.createPasswordPlaceholder")}
                  autoComplete="new-password"
                  required
                />
              </div>
            </div>

            <div className="mt-2 flex gap-2">
              <Button type="button" onClick={() => router.push("/admin/users")}>
                {t("admin.users.editUserModal.cancelButton")}
              </Button>
              <CreateButton primary type="submit" disabled={disabled}>
                {isSubmitting
                  ? t("admin.users.creatingButton")
                  : t("admin.users.addUserButton")}
              </CreateButton>
            </div>
          </div>
        </form>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
