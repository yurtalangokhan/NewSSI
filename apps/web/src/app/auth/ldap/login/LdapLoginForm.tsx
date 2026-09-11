"use client";

import { toast } from "@/hooks/useToast";
import { ldapLogin } from "@/lib/user";
import Button from "@/refresh-components/buttons/Button";
import { Form, Formik } from "formik";
import * as Yup from "yup";
import { useState } from "react";
import { FormikField } from "@/refresh-components/form/FormikField";
import { FormField } from "@/refresh-components/form/FormField";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import PasswordInputTypeIn from "@/refresh-components/inputs/PasswordInputTypeIn";
import { validateInternalRedirect } from "@/lib/auth/redirectValidation";
import { APIFormFieldState } from "@/refresh-components/form/types";
import { SvgArrowRightCircle } from "@opal/icons";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";

export default function LdapLoginForm() {
  const { t } = useTranslation();
  const [isWorking, setIsWorking] = useState<boolean>(false);
  const [apiStatus, setApiStatus] = useState<APIFormFieldState>("loading");
  const [showApiMessage, setShowApiMessage] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string>("");

  const apiMessages = {
    loading: t("auth.signingIn"),
    success: t("auth.signedInSuccessfully"),
    error: errorMessage,
  };

  const readErrorMessage = async (response: Response): Promise<string> => {
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      if (typeof detail === "string") return detail;
      if (typeof detail === "object" && detail?.reason) return detail.reason;
    } catch {
      /* fallback */
    }
    try {
      return (await response.text()).trim();
    } catch {
      return "";
    }
  };

  return (
    <>
      <div className="flex flex-col items-center w-full mb-6">
        <Text as="h1" className="text-xl font-semibold text-white">
          {t("ldapLogin.title")}
        </Text>
        <Text as="p" className="text-sm text-white/60 mt-1">
          {t("ldapLogin.subtitle")}
        </Text>
      </div>

      <Formik
        initialValues={{ username: "", password: "" }}
        validateOnChange={true}
        validateOnBlur={true}
        validationSchema={Yup.object().shape({
          username: Yup.string().required(t("auth.usernameRequired")),
          password: Yup.string().required(t("auth.passwordRequired")),
        })}
        onSubmit={async (values) => {
          setShowApiMessage(true);
          setApiStatus("loading");
          setErrorMessage("");

          let loginResponse: Response;
          try {
            loginResponse = await ldapLogin(values.username, values.password);
          } catch {
            setIsWorking(false);
            const errorMsg = t("auth.unknownError");
            setErrorMessage(errorMsg);
            setApiStatus("error");
            toast.error(t("auth.toastLoginFailed", { error: errorMsg }));
            return;
          }

          if (loginResponse.ok) {
            setApiStatus("success");
            const validatedNextUrl = validateInternalRedirect(null);
            window.location.href = validatedNextUrl || "/app";
          } else {
            setIsWorking(false);
            const errorDetail = await readErrorMessage(loginResponse);
            let errorMsg: string = t("auth.unknownError");
            if (errorDetail === "LOGIN_BAD_CREDENTIALS") {
              errorMsg = t("auth.invalidCredentials");
            } else if (errorDetail) {
              errorMsg = errorDetail;
            }
            if (loginResponse.status === 429) {
              errorMsg = t("auth.tooManyRequests");
            }
            setErrorMessage(errorMsg);
            setApiStatus("error");
            toast.error(t("auth.toastLoginFailed", { error: errorMsg }));
          }
        }}
      >
        {({ isSubmitting, isValid, dirty }) => (
          <Form className="flex flex-col gap-5 w-full">
            <FormikField<string>
              name="username"
              render={(field, helper, _meta, state) => (
                <FormField name="username" state={state} className="w-full">
                  <FormField.Label className="text-white font-medium text-sm mb-2 block">
                    {t("auth.usernameLabel")}
                  </FormField.Label>
                  <FormField.Control>
                    <InputTypeIn
                      {...field}
                      onChange={(e) => {
                        if (showApiMessage && apiStatus === "error") {
                          setShowApiMessage(false);
                          setErrorMessage("");
                          setApiStatus("loading");
                        }
                        field.onChange(e);
                      }}
                      placeholder={t("auth.usernamePlaceholder")}
                      onClear={() => helper.setValue("")}
                      data-testid="username"
                      variant={apiStatus === "error" ? "error" : undefined}
                      showClearButton={false}
                    />
                  </FormField.Control>
                </FormField>
              )}
            />

            <FormikField<string>
              name="password"
              render={(field, helper, _meta, state) => (
                <FormField name="password" state={state} className="w-full">
                  <FormField.Label className="text-white font-medium text-sm mb-2 block">
                    Password
                  </FormField.Label>
                  <FormField.Control>
                    <PasswordInputTypeIn
                      {...field}
                      onChange={(e) => {
                        if (showApiMessage && apiStatus === "error") {
                          setShowApiMessage(false);
                          setErrorMessage("");
                          setApiStatus("loading");
                        }
                        field.onChange(e);
                      }}
                      placeholder="∗∗∗∗∗∗∗∗∗∗∗∗∗∗"
                      onClear={() => helper.setValue("")}
                      data-testid="password"
                      error={apiStatus === "error"}
                      showClearButton={false}
                      style={{ color: "var(--text-05)" }}
                    />
                  </FormField.Control>
                  {showApiMessage && (
                    <FormField.APIMessage
                      state={apiStatus}
                      messages={apiMessages}
                    />
                  )}
                </FormField>
              )}
            />

            <Button
              type="submit"
              className="w-full mt-3 py-3 bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 text-white font-semibold rounded-lg transition-all duration-200 hover:shadow-lg"
              disabled={isSubmitting || !isValid || !dirty}
              rightIcon={SvgArrowRightCircle}
            >
              {t("auth.signInButton")}
            </Button>
          </Form>
        )}
      </Formik>
    </>
  );
}
