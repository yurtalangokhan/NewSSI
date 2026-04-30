"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_PATHS, ADMIN_ROUTE_CONFIG } from "@/lib/admin-routes";
import { toast } from "@/hooks/useToast";
import Button from "@/refresh-components/buttons/Button";
import CreateButton from "@/refresh-components/buttons/CreateButton";
import Text from "@/refresh-components/texts/Text";

const usersRoute = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.USERS]!;

const ROLE_OPTIONS = ["basic", "admin", "limited", "curator", "global_curator"];

export default function AddUserPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [role, setRole] = useState("basic");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const disabled = useMemo(() => {
    return isSubmitting || !email.trim() || !email.includes("@");
  }, [email, isSubmitting]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (disabled) return;

    setIsSubmitting(true);
    try {
      const response = await fetch("/api/manage/admin/create-user", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          first_name: firstName.trim() || undefined,
          last_name: lastName.trim() || undefined,
          role,
          password: password.trim() || undefined,
        }),
      });

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        const detail = errorBody?.detail || "Unknown error";
        throw new Error(detail);
      }

      toast.success("User created and synced with Keycloak");
      router.push("/admin/users");
      router.refresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      toast.error(`Failed to create user - ${message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        title={`${usersRoute.title} - Add User`}
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
              Create a user directly in the platform. This action also creates and syncs
              the account in Keycloak.
            </Text>

            <label className="flex flex-col gap-1">
              <Text as="p" mainUiBody>
                Email
              </Text>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="h-10 rounded border border-border-subtle bg-background px-3"
                placeholder="user@example.com"
                required
              />
            </label>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="flex flex-col gap-1">
                <Text as="p" mainUiBody>
                  First Name
                </Text>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="h-10 rounded border border-border-subtle bg-background px-3"
                  placeholder="John"
                />
              </label>

              <label className="flex flex-col gap-1">
                <Text as="p" mainUiBody>
                  Last Name
                </Text>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="h-10 rounded border border-border-subtle bg-background px-3"
                  placeholder="Doe"
                />
              </label>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="flex flex-col gap-1">
                <Text as="p" mainUiBody>
                  Role
                </Text>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="h-10 rounded border border-border-subtle bg-background px-3"
                >
                  {ROLE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <Text as="p" mainUiBody>
                  Password (optional)
                </Text>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-10 rounded border border-border-subtle bg-background px-3"
                  placeholder="Leave empty to set later"
                />
              </label>
            </div>

            <div className="mt-2 flex gap-2">
              <Button type="button" onClick={() => router.push("/admin/users")}>
                Cancel
              </Button>
              <CreateButton primary type="submit" disabled={disabled}>
                {isSubmitting ? "Creating..." : "Create User"}
              </CreateButton>
            </div>
          </div>
        </form>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
