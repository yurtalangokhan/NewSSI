"use client";
import React, { useState } from "react";
import { forgotPassword } from "./utils";
import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import Title from "@/components/ui/title";
import Text from "@/components/ui/text";
import Link from "next/link";
import Button from "@/refresh-components/buttons/Button";
import { Form, Formik } from "formik";
import * as Yup from "yup";
import { TextFormField } from "@/components/Field";
import { toast } from "@/hooks/useToast";
import { redirect } from "next/navigation";
import { NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED } from "@/lib/constants";
import { useTranslation } from "react-i18next";

const ForgotPasswordPage: React.FC = () => {
  const [isWorking, setIsWorking] = useState(false);
  const { t } = useTranslation();

  if (!NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED) {
    redirect("/auth/login");
  }

  return (
    <AuthFlowContainer>
      <div className="flex flex-col w-full justify-center">
        <div className="flex">
          <Title className="mb-2 mx-auto font-bold">
            {t("auth.forgotPassword.title")}
          </Title>
        </div>

        <Formik
          initialValues={{
            email: "",
          }}
          validationSchema={Yup.object().shape({
            email: Yup.string().email().required(),
          })}
          onSubmit={async (values) => {
            setIsWorking(true);
            try {
              await forgotPassword(values.email);
              toast.success(t("auth.forgotPassword.toastEmailSent"));
            } catch (error) {
              const errorMessage =
                error instanceof Error
                  ? error.message
                  : t("auth.forgotPassword.toastError");
              toast.error(errorMessage);
            } finally {
              setIsWorking(false);
            }
          }}
        >
          {({ isSubmitting }) => (
            <Form className="w-full flex flex-col items-stretch mt-2">
              <TextFormField
                name="email"
                label={t("auth.forgotPassword.emailLabel")}
                type="email"
                placeholder={t("auth.emailPlaceholder")}
              />

              <div className="flex">
                <Button
                  type="submit"
                  disabled={isSubmitting}
                  className="mx-auto w-full"
                >
                  {t("auth.forgotPassword.resetButton")}
                </Button>
              </div>
            </Form>
          )}
        </Formik>
        <div className="flex">
          <Text className="mt-4 mx-auto">
            <Link href="/auth/login" className="text-link font-medium">
              {t("auth.forgotPassword.backToLogin")}
            </Link>
          </Text>
        </div>
      </div>
    </AuthFlowContainer>
  );
};

export default ForgotPasswordPage;
