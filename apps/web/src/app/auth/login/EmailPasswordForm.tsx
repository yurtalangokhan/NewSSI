"use client";

import { toast } from "@/hooks/useToast";
import { basicLogin, basicSignup } from "@/lib/user";
import Button from "@/refresh-components/buttons/Button";
import { Form, Formik } from "formik";
import * as Yup from "yup";
import { requestEmailVerification } from "../lib";
import { useMemo, useState } from "react";
import { Spinner } from "@/components/Spinner";
import Link from "next/link";
import { useUser } from "@/providers/UserProvider";
import { FormikField } from "@/refresh-components/form/FormikField";
import { FormField } from "@/refresh-components/form/FormField";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import PasswordInputTypeIn from "@/refresh-components/inputs/PasswordInputTypeIn";
import { validateInternalRedirect } from "@/lib/auth/redirectValidation";
import { APIFormFieldState } from "@/refresh-components/form/types";
import { SvgArrowRightCircle } from "@opal/icons";
import { useCaptcha } from "@/lib/hooks/useCaptcha";
import { useTranslation } from "react-i18next";

interface EmailPasswordFormProps {
  isSignup?: boolean;
  shouldVerify?: boolean;
  referralSource?: string;
  nextUrl?: string | null;
  defaultEmail?: string | null;
  isJoin?: boolean;
}

export default function EmailPasswordForm({
  isSignup = false,
  shouldVerify,
  referralSource,
  nextUrl,
  defaultEmail,
  isJoin = false,
}: EmailPasswordFormProps) {
  const { user } = useUser();
  const { t } = useTranslation();
  const [isWorking, setIsWorking] = useState<boolean>(false);
  const [apiStatus, setApiStatus] = useState<APIFormFieldState>("loading");
  const [showApiMessage, setShowApiMessage] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const { getCaptchaToken } = useCaptcha();

  const apiMessages = useMemo(
    () => ({
      loading: isSignup
        ? isJoin
          ? t("auth.joining")
          : t("auth.creatingAccount")
        : t("auth.signingIn"),
      success: isSignup
        ? t("auth.accountCreatedSigningIn")
        : t("auth.signedInSuccessfully"),
      error: errorMessage,
    }),
    [isSignup, isJoin, errorMessage, t]
  );

  const readErrorMessage = async (response: Response): Promise<string> => {
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (typeof detail === "object" && detail?.reason) {
        return detail.reason;
      }
    } catch {
      // Fall back to raw text below.
    }

    try {
      return (await response.text()).trim();
    } catch {
      return "";
    }
  };

  return (
    <>
      {isWorking && <Spinner />}

      <Formik
        initialValues={{
          username: "",
          password: "",
          ...(isSignup ? { email: defaultEmail ? defaultEmail.toLowerCase() : "", firstName: "", lastName: "" } : {}),
        }}
        validateOnChange={true}
        validateOnBlur={true}
        validationSchema={Yup.object().shape({
          username: Yup.string()
            .required(t("auth.usernameRequired")),
          ...(isSignup
            ? {
                email: Yup.string()
                  .email()
                  .required()
                  .transform((value) => value.toLowerCase()),
                firstName: Yup.string().trim().required(),
                lastName: Yup.string().trim().required(),
              }
            : {}),
          password: Yup.string()
            .required(),
        })}
        onSubmit={async (values: { username: string; password: string; email?: string; firstName?: string; lastName?: string }) => {
          const username: string = values.username;
          const email: string = values.email?.toLowerCase() || "";
          setShowApiMessage(true);
          setApiStatus("loading");
          setErrorMessage("");

          if (isSignup) {
            // login is fast, no need to show a spinner
            setIsWorking(true);

            // Get captcha token for signup (if captcha is enabled)
            const captchaToken = await getCaptchaToken("signup");

            let response: Response;
            try {
              response = await basicSignup(
                email,
                values.password,
                referralSource,
                captchaToken,
                username,
                values.firstName?.trim() || "",
                values.lastName?.trim() || ""
              );
            } catch {
              setIsWorking(false);
              const errorMsg = t("auth.unknownError");
              setErrorMessage(errorMsg);
              setApiStatus("error");
              toast.error(t("auth.toastSignUpFailed", { error: errorMsg }));
              return;
            }

            if (!response.ok) {
              setIsWorking(false);

              let errorMsg: string = t("auth.unknownError");
              let errorDetail: any = null;
              try {
                const responseData: any = await response.json();
                errorDetail = responseData.detail;

                if (typeof errorDetail === "object") {
                  if (errorDetail.reason) {
                    errorMsg = errorDetail.reason;
                  } else if (Array.isArray(errorDetail)) {
                    // Handle Pydantic validation errors (array format)
                    const messages = errorDetail
                      .map((err: any) => err.msg || err.message || String(err))
                      .filter(Boolean);
                    errorMsg = messages.join(", ");
                  }
                } else if (errorDetail === "REGISTER_USER_ALREADY_EXISTS") {
                  errorMsg = t("auth.accountAlreadyExists");
                } else if (typeof errorDetail === "string") {
                  errorMsg = errorDetail;
                }
              } catch (e) {
                // If JSON parsing fails, keep the unknown error message
              }

              if (response.status === 429) {
                errorMsg = t("auth.tooManyRequests");
              }
              setErrorMessage(errorMsg);
              setApiStatus("error");
              toast.error(t("auth.toastSignUpFailed", { error: errorMsg }));
              setIsWorking(false);
              return;
            } else {
              setApiStatus("success");
              toast.success(t("auth.toastAccountCreated"));

              if (isSignup && shouldVerify) {
                await requestEmailVerification(email);
                // Use window.location.href to force a full page reload,
                // ensuring app re-initializes with the new state (including
                // server-side provider values)
                window.location.href = "/auth/waiting-on-verification";
                return;
              }

              // The searchparam is purely for multi tenant developement purposes.
              // It replicates the behavior of the case where a user
              // has signed up with email / password as the only user to an instance
              // and has just completed verification
              const validatedNextUrl = validateInternalRedirect(nextUrl);
              window.location.href = validatedNextUrl
                ? validatedNextUrl
                : `/app${isSignup && !isJoin ? "?new_team=true" : ""}`;
              return;
            }
          }

          let loginResponse: Response;
          try {
            loginResponse = await basicLogin(username, values.password);
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
            if (isSignup && shouldVerify) {
              await requestEmailVerification(email);
              // Use window.location.href to force a full page reload,
              // ensuring app re-initializes with the new state (including
              // server-side provider values)
              window.location.href = "/auth/waiting-on-verification";
            } else {
              // The searchparam is purely for multi tenant developement purposes.
              // It replicates the behavior of the case where a user
              // has signed up with email / password as the only user to an instance
              // and has just completed verification
              const validatedNextUrl = validateInternalRedirect(nextUrl);
              window.location.href = validatedNextUrl
                ? validatedNextUrl
                : `/app${isSignup && !isJoin ? "?new_team=true" : ""}`;
            }
          } else {
            setIsWorking(false);
            const errorDetail = await readErrorMessage(loginResponse);
            let errorMsg: string = t("auth.unknownError");
            if (errorDetail === "LOGIN_BAD_CREDENTIALS") {
              errorMsg = t("auth.invalidCredentials");
            } else if (errorDetail === "NO_WEB_LOGIN_AND_HAS_NO_PASSWORD") {
              errorMsg = t("auth.noPasswordSet");
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
        {({ isSubmitting, isValid, dirty, values }) => {
          return (
            <Form className="flex flex-col gap-5 w-full">
              <FormikField<string>
                name="username"
                render={(field, helper, _meta, state) => (
                  <FormField name="username" state={state} className="w-full">
                    <FormField.Label className="text-white font-medium text-sm mb-2 block">{t("auth.usernameLabel")}</FormField.Label>
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
              {isSignup && (
                <FormikField<string>
                  name="email"
                  render={(field, helper, _meta, state) => (
                    <FormField name="email" state={state} className="w-full">
                      <FormField.Label className="text-white font-medium text-sm mb-2 block">{t("auth.emailLabel")}</FormField.Label>
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
                          placeholder={t("auth.emailPlaceholder")}
                          onClear={() => helper.setValue("")}
                          data-testid="email"
                          variant={apiStatus === "error" ? "error" : undefined}
                          showClearButton={false}
                        />
                      </FormField.Control>
                    </FormField>
                  )}
                />
              )}

              {isSignup && (
                <div className="flex gap-3 w-full">
                  <FormikField<string>
                    name="firstName"
                    render={(field, helper, _meta, state) => (
                      <FormField name="firstName" state={state} className="w-full">
                        <FormField.Label className="text-white font-medium text-sm mb-2 block">{t("auth.firstNameLabel") || "First Name"}</FormField.Label>
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
                            placeholder="John"
                            onClear={() => helper.setValue("")}
                            data-testid="firstName"
                            showClearButton={false}
                          />
                        </FormField.Control>
                      </FormField>
                    )}
                  />
                  <FormikField<string>
                    name="lastName"
                    render={(field, helper, _meta, state) => (
                      <FormField name="lastName" state={state} className="w-full">
                        <FormField.Label className="text-white font-medium text-sm mb-2 block">{t("auth.lastNameLabel") || "Last Name"}</FormField.Label>
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
                            placeholder="Doe"
                            onClear={() => helper.setValue("")}
                            data-testid="lastName"
                            showClearButton={false}
                          />
                        </FormField.Control>
                      </FormField>
                    )}
                  />
                </div>
              )}

              <FormikField<string>
                name="password"
                render={(field, helper, _meta, state) => (
                  <FormField name="password" state={state} className="w-full">
                    <FormField.Label className="text-white font-medium text-sm mb-2 block">Password</FormField.Label>
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
                        style={{ color: 'var(--text-05)' }}
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
                {isJoin ? t("auth.joinButton") : isSignup ? t("auth.createAccountButton") : t("auth.signInButton")}
              </Button>
              {user?.is_anonymous_user && (
                <Link
                  href="/app"
                  className="text-xs text-white/60 cursor-pointer text-center w-full font-medium mx-auto py-3 hover:text-white transition-colors duration-200"
                >
                  <span className="hover:border-b hover:border-dotted hover:border-white">
                    {t("auth.continueAsGuest")}
                  </span>
                </Link>
              )}
              {isSignup && (
                <div className="text-sm text-center w-full text-white/60 mt-4">
                  Already have an account?{" "}
                  <Link
                    href="/auth/login"
                    className="text-white font-medium underline hover:text-white/90 transition-colors duration-200"
                  >
                    Sign In
                  </Link>
                </div>
              )}
            </Form>
          );
        }}
      </Formik>
    </>
  );
}
