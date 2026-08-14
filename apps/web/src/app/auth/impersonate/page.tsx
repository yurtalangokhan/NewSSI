"use client";

import AuthFlowContainer from "@/components/auth/AuthFlowContainer";

import { useUser } from "@/providers/UserProvider";
import { redirect, useRouter } from "next/navigation";
import type { Route } from "next";
import { Formik, Form, FormikHelpers } from "formik";
import * as Yup from "yup";
import { toast } from "@/hooks/useToast";
import { TextFormField } from "@/components/Field";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";

const ImpersonateSchema = Yup.object().shape({
  email: Yup.string().email("Invalid email").required("Required"),
  apiKey: Yup.string().required("Required"),
});

export default function ImpersonatePage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { user, hasPermission } = useUser();
  if (!user) {
    redirect("/auth/login");
  }

  if (!hasPermission("user:impersonate")) {
    redirect("/app" as Route);
  }

  const handleImpersonate = async (
    values: { email: string; apiKey: string },
    helpers: FormikHelpers<{ email: string; apiKey: string }>
  ) => {
    try {
      const response = await fetch("/api/tenants/impersonate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${values.apiKey}`,
        },
        body: JSON.stringify({ email: values.email }),
        credentials: "same-origin",
      });

      if (!response.ok) {
        const errorData = await response.json();
        toast.error(errorData.detail || "Failed to impersonate user");
        helpers.setSubmitting(false);
      } else {
        helpers.setSubmitting(false);
        router.push("/app" as Route);
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to impersonate user"
      );
      helpers.setSubmitting(false);
    }
  };

  return (
    <AuthFlowContainer>
      <div className="flex flex-col w-full justify-center">
        <div className="w-full flex flex-col items-center justify-center">
          <Text as="p" headingH3 className="mb-6 text-center">
            {t("authPages.impersonate.title")}
          </Text>
        </div>

        <Formik
          initialValues={{ email: "", apiKey: "" }}
          validationSchema={ImpersonateSchema}
          onSubmit={(values, helpers) => handleImpersonate(values, helpers)}
        >
          {({ isSubmitting }) => (
            <Form className="flex flex-col gap-4">
              <TextFormField
                name="email"
                type="email"
                label={t("auth.emailLabel")}
                placeholder={t("auth.emailPlaceholder")}
              />

              <TextFormField
                name="apiKey"
                type="password"
                label={t("authPages.impersonate.apiKeyLabel")}
                placeholder={t("authPages.impersonate.apiKeyPlaceholder")}
              />

              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {t("authPages.impersonate.submitButton")}
              </Button>
            </Form>
          )}
        </Formik>

        <Text as="p" mainUiMuted text03 className="mt-4 text-center px-4">
          {t("authPages.impersonate.adminNote")}
        </Text>
      </div>
    </AuthFlowContainer>
  );
}
