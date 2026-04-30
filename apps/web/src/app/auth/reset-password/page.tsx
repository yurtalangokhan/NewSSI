"use client";
import React, { useState, useEffect } from "react";
import { resetPassword } from "../forgot-password/utils";
import AuthFlowContainer from "@/components/auth/AuthFlowContainer";
import Title from "@/components/ui/title";
import Text from "@/components/ui/text";
import Link from "next/link";
import Button from "@/refresh-components/buttons/Button";
import { Form, Formik } from "formik";
import * as Yup from "yup";
import { TextFormField } from "@/components/Field";
import { toast } from "@/hooks/useToast";
import { Spinner } from "@/components/Spinner";
import { redirect, useSearchParams } from "next/navigation";
import {
  NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED,
  TENANT_ID_COOKIE_NAME,
} from "@/lib/constants";
import Cookies from "js-cookie";
import { useTranslation } from "react-i18next";

const ResetPasswordPage: React.FC = () => {
  const [isWorking, setIsWorking] = useState(false);
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const token = searchParams?.get("token");
  const tenantId = searchParams?.get(TENANT_ID_COOKIE_NAME);

  useEffect(() => {
    if (tenantId) {
      Cookies.set(TENANT_ID_COOKIE_NAME, tenantId, {
        path: "/",
        expires: 1 / 24,
      });
    }
  }, [tenantId]);

  if (!NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED) {
    redirect("/auth/login");
  }

  return (
    <AuthFlowContainer>
      <div className="flex flex-col w-full justify-center">
        <div className="flex">
          <Title className="mb-2 mx-auto font-bold">{t("auth.resetPassword.title")}</Title>
        </div>
        {isWorking && <Spinner />}
        <Formik
          initialValues={{
            password: "",
            confirmPassword: "",
          }}
          validationSchema={Yup.object().shape({
            password: Yup.string().required(t("auth.resetPassword.passwordRequired")),
            confirmPassword: Yup.string()
              .oneOf([Yup.ref("password"), undefined], t("auth.resetPassword.confirmPasswordMismatch"))
              .required(t("auth.resetPassword.confirmPasswordRequired")),
          })}
          onSubmit={async (values) => {
            if (!token) {
              toast.error(t("auth.resetPassword.toastMissingToken"));
              return;
            }
            setIsWorking(true);
            try {
              await resetPassword(token, values.password);
              toast.success(t("auth.resetPassword.toastResetSuccess"));
              setTimeout(() => {
                redirect("/auth/login");
              }, 1000);
            } catch (error) {
              if (error instanceof Error) {
                toast.error(
                  error.message || t("auth.resetPassword.toastResetError")
                );
              } else {
                toast.error(t("auth.resetPassword.toastUnexpectedError"));
              }
            } finally {
              setIsWorking(false);
            }
          }}
        >
          {({ isSubmitting }) => (
            <Form className="w-full flex flex-col items-stretch mt-2">
              <TextFormField
                name="password"
                label={t("auth.resetPassword.newPasswordLabel")}
                type="password"
                placeholder={t("auth.resetPassword.newPasswordPlaceholder")}
              />
              <TextFormField
                name="confirmPassword"
                label={t("auth.resetPassword.confirmPasswordLabel")}
                type="password"
                placeholder={t("auth.resetPassword.confirmPasswordPlaceholder")}
              />

              <div className="flex">
                <Button
                  type="submit"
                  disabled={isSubmitting}
                  className="mx-auto w-full"
                >
                  {t("auth.resetPassword.resetButton")}
                </Button>
              </div>
            </Form>
          )}
        </Formik>
        <div className="flex">
          <Text className="mt-4 mx-auto">
            <Link href="/auth/login" className="text-link font-medium">
              {t("auth.resetPassword.backToLogin")}
            </Link>
          </Text>
        </div>
      </div>
    </AuthFlowContainer>
  );
};

export default ResetPasswordPage;
