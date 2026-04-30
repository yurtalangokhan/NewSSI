import { toast } from "@/hooks/useToast";
import React, { useState, useEffect } from "react";
import { useSWRConfig } from "swr";
import * as Yup from "yup";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { adminDeleteCredential } from "@/lib/credential";
import { setupGoogleDriveOAuth } from "@/lib/googleDrive";
import {
  DOCS_ADMINS_PATH,
  GOOGLE_DRIVE_AUTH_IS_ADMIN_COOKIE_NAME,
} from "@/lib/constants";
import Cookies from "js-cookie";
import { TextFormField, SectionHeader } from "@/components/Field";
import { Form, Formik } from "formik";
import { User } from "@/lib/types";
import Button from "@/refresh-components/buttons/Button";
import {
  Credential,
  GoogleDriveCredentialJson,
  GoogleDriveServiceAccountCredentialJson,
} from "@/lib/connectors/credentials";
import { refreshAllGoogleData } from "@/lib/googleConnector";
import { ValidSources } from "@/lib/types";
import { buildSimilarCredentialInfoURL } from "@/app/admin/connector/[ccPairId]/lib";
import { FiFile, FiCheck, FiLink, FiAlertTriangle } from "react-icons/fi";
import { cn, truncateString } from "@/lib/utils";
import { useTranslation } from "react-i18next";

type GoogleDriveCredentialJsonTypes = "authorized_user" | "service_account";

export const DriveJsonUpload = ({ onSuccess }: { onSuccess?: () => void }) => {
  const { t } = useTranslation();
  const { mutate } = useSWRConfig();
  const [isUploading, setIsUploading] = useState(false);
  const [fileName, setFileName] = useState<string | undefined>();
  const [isDragging, setIsDragging] = useState(false);

  const handleFileUpload = async (file: File) => {
    setIsUploading(true);
    setFileName(file.name);

    const reader = new FileReader();
    reader.onload = async (loadEvent) => {
      if (!loadEvent?.target?.result) {
        setIsUploading(false);
        return;
      }

      const credentialJsonStr = loadEvent.target.result as string;

      // Check credential type
      let credentialFileType: GoogleDriveCredentialJsonTypes;
      try {
        const appCredentialJson = JSON.parse(credentialJsonStr);
        if (appCredentialJson.web) {
          credentialFileType = "authorized_user";
        } else if (appCredentialJson.type === "service_account") {
          credentialFileType = "service_account";
        } else {
          throw new Error(
            "Unknown credential type, expected one of 'OAuth Web application' or 'Service Account'"
          );
        }
      } catch (e) {
        toast.error(`Invalid file provided - ${e}`);
        setIsUploading(false);
        return;
      }

      if (credentialFileType === "authorized_user") {
        const response = await fetch(
          "/api/manage/admin/connector/google-drive/app-credential",
          {
            method: "PUT",
            headers: {
              "Content-Type": "application/json",
            },
            body: credentialJsonStr,
          }
        );
        if (response.ok) {
          toast.success(t("googleCredentials.uploadAppCredentials"));
          mutate("/api/manage/admin/connector/google-drive/app-credential");
          if (onSuccess) {
            onSuccess();
          }
        } else {
          const errorMsg = await response.text();
          toast.error(t("googleCredentials.failedUploadAppCredentials", { errorMsg }));
        }
      }

      if (credentialFileType === "service_account") {
        const response = await fetch(
          "/api/manage/admin/connector/google-drive/service-account-key",
          {
            method: "PUT",
            headers: {
              "Content-Type": "application/json",
            },
            body: credentialJsonStr,
          }
        );
        if (response.ok) {
          toast.success("Successfully uploaded service account key");
          mutate(
            "/api/manage/admin/connector/google-drive/service-account-key"
          );
          if (onSuccess) {
            onSuccess();
          }
        } else {
          const errorMsg = await response.text();
          toast.error(`Failed to upload service account key - ${errorMsg}`);
        }
      }
      setIsUploading(false);
    };

    reader.readAsText(file);
  };

  const handleDragEnter = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isUploading) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (isUploading) return;

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      if (
        file !== undefined &&
        (file.type === "application/json" || file.name.endsWith(".json"))
      ) {
        handleFileUpload(file);
      } else {
        toast.error(t("googleCredentials.pleaseUploadJson"));
      }
    }
  };

  return (
    <div className="flex flex-col mt-4">
      <div className="flex items-center">
        <div className="relative flex flex-1 items-center">
          <label
            className={cn(
              "flex h-10 items-center justify-center w-full px-4 py-2 border border-dashed rounded-md transition-colors",
              isUploading
                ? "opacity-70 cursor-not-allowed border-background-400 bg-background-50/30"
                : isDragging
                  ? "bg-background-50/50 border-primary dark:border-primary"
                  : "cursor-pointer hover:bg-background-50/30 hover:border-primary dark:hover:border-primary border-background-300 dark:border-background-600"
            )}
            onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            <div className="flex items-center space-x-2">
              {isUploading ? (
                <div className="h-4 w-4 border-t-2 border-b-2 border-primary rounded-full animate-spin"></div>
              ) : (
                <FiFile className="h-4 w-4 text-text-500" />
              )}
              <span className="text-sm text-text-500">
                {isUploading
                  ? t("googleCredentials.uploading", { fileName: truncateString(fileName || "file", 50) })
                    : isDragging
                    ? t("googleCredentials.dropJsonHere")
                    : truncateString(
                        fileName || t("googleCredentials.selectOrDragJson"),
                        50
                      )}
              </span>
            </div>
            <input
              className="sr-only"
              type="file"
              accept=".json"
              disabled={isUploading}
              onChange={(event) => {
                if (!event.target.files?.length) {
                  return;
                }
                const file = event.target.files[0];
                if (file === undefined) {
                  return;
                }
                handleFileUpload(file);
              }}
            />
          </label>
        </div>
      </div>
    </div>
  );
};

interface DriveJsonUploadSectionProps {
  appCredentialData?: { client_id: string };
  serviceAccountCredentialData?: { service_account_email: string };
  isAdmin: boolean;
  onSuccess?: () => void;
  existingAuthCredential?: boolean;
}

export const DriveJsonUploadSection = ({
  appCredentialData,
  serviceAccountCredentialData,
  isAdmin,
  onSuccess,
  existingAuthCredential,
}: DriveJsonUploadSectionProps) => {  const { t } = useTranslation();  const { mutate } = useSWRConfig();
  const router = useRouter();
  const [localServiceAccountData, setLocalServiceAccountData] = useState(
    serviceAccountCredentialData
  );
  const [localAppCredentialData, setLocalAppCredentialData] =
    useState(appCredentialData);

  // Update local state when props change
  useEffect(() => {
    setLocalServiceAccountData(serviceAccountCredentialData);
    setLocalAppCredentialData(appCredentialData);
  }, [serviceAccountCredentialData, appCredentialData]);

  const handleSuccess = () => {
    if (onSuccess) {
      onSuccess();
    } else {
      refreshAllGoogleData(ValidSources.GoogleDrive);
    }
  };

  if (!isAdmin) {
    return (
      <div>
        <div className="flex items-start py-3 px-4 bg-yellow-50/30 dark:bg-yellow-900/5 rounded">
          <FiAlertTriangle className="text-yellow-500 h-5 w-5 mr-2 mt-0.5 flex-shrink-0" />
          <p className="text-sm">
            {t("googleCredentials.curatorsCannotSetupDrive")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <p className="text-sm mb-3">
        {t("googleCredentials.connectDriveDesc")}
      </p>
      <div className="mb-4">
        <a
          className="text-primary hover:text-primary/80 flex items-center gap-1 text-sm"
          target="_blank"
          href={`${DOCS_ADMINS_PATH}/connectors/official/google_drive/overview`}
          rel="noreferrer"
        >
          <FiLink className="h-3 w-3" />
          {t("googleCredentials.viewSetupInstructions")}
        </a>
      </div>

      {(localServiceAccountData?.service_account_email ||
        localAppCredentialData?.client_id) && (
        <div className="mb-4">
          <div className="relative flex flex-1 items-center">
            <label
              className={cn(
                "flex h-10 items-center justify-center w-full px-4 py-2 border border-dashed rounded-md transition-colors",
                false
                  ? "opacity-70 cursor-not-allowed border-background-400 bg-background-50/30"
                  : "cursor-pointer hover:bg-background-50/30 hover:border-primary dark:hover:border-primary border-background-300 dark:border-background-600"
              )}
            >
              <div className="flex items-center space-x-2">
                {false ? (
                  <div className="h-4 w-4 border-t-2 border-b-2 border-primary rounded-full animate-spin"></div>
                ) : (
                  <FiFile className="h-4 w-4 text-text-500" />
                )}
                <span className="text-sm text-text-500">
                  {truncateString(
                    localServiceAccountData?.service_account_email ||
                      localAppCredentialData?.client_id ||
                      "",
                    50
                  )}
                </span>
              </div>
            </label>
          </div>
          {isAdmin && !existingAuthCredential && (
            <div className="mt-2">
              <Button
                danger
                onClick={async () => {
                  const endpoint =
                    localServiceAccountData?.service_account_email
                      ? "/api/manage/admin/connector/google-drive/service-account-key"
                      : "/api/manage/admin/connector/google-drive/app-credential";

                  const response = await fetch(endpoint, {
                    method: "DELETE",
                  });

                  if (response.ok) {
                    mutate(endpoint);
                    // Also mutate the credential endpoints to ensure Step 2 is reset
                    mutate(
                      buildSimilarCredentialInfoURL(ValidSources.GoogleDrive)
                    );

                    // Add additional mutations to refresh all credential-related endpoints
                    mutate(
                      "/api/manage/admin/connector/google-drive/credentials"
                    );
                    mutate(
                      "/api/manage/admin/connector/google-drive/public-credential"
                    );
                    mutate(
                      "/api/manage/admin/connector/google-drive/service-account-credential"
                    );

                    toast.success(
                      t("googleCredentials.successDeletedCredentials", {
                        type: localServiceAccountData
                          ? t("googleCredentials.serviceAccountKey")
                          : t("googleCredentials.appCredentials"),
                      })
                    );
                    // Immediately update local state
                    if (localServiceAccountData) {
                      setLocalServiceAccountData(undefined);
                    } else {
                      setLocalAppCredentialData(undefined);
                    }
                    handleSuccess();
                  } else {
                    const errorMsg = await response.text();
                    toast.error(t("googleCredentials.failedDeleteCredentials", { errorMsg }));
                  }
                }}
              >
                {t("googleCredentials.deleteCredentials")}
              </Button>
            </div>
          )}
        </div>
      )}

      {!(
        localServiceAccountData?.service_account_email ||
        localAppCredentialData?.client_id
      ) && <DriveJsonUpload onSuccess={handleSuccess} />}
    </div>
  );
};

interface DriveCredentialSectionProps {
  googleDrivePublicUploadedCredential?: Credential<GoogleDriveCredentialJson>;
  googleDriveServiceAccountCredential?: Credential<GoogleDriveServiceAccountCredentialJson>;
  serviceAccountKeyData?: { service_account_email: string };
  appCredentialData?: { client_id: string };
  refreshCredentials: () => void;
  connectorAssociated: boolean;
  user: User | null;
}

async function handleRevokeAccess(
  connectorAssociated: boolean,
  existingCredential:
    | Credential<GoogleDriveCredentialJson>
    | Credential<GoogleDriveServiceAccountCredentialJson>,
  refreshCredentials: () => void,
  t: (key: string) => string
) {
  if (connectorAssociated) {
    toast.error(t("googleCredentials.revokeDriveError"));
    return;
  }

  await adminDeleteCredential(existingCredential.id);
  toast.success(t("googleCredentials.revokedDrive"));

  refreshCredentials();
}

export const DriveAuthSection = ({
  googleDrivePublicUploadedCredential,
  googleDriveServiceAccountCredential,
  serviceAccountKeyData,
  appCredentialData,
  refreshCredentials,
  connectorAssociated,
  user,
}: DriveCredentialSectionProps) => {
  const { t } = useTranslation();
  const router = useRouter();
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [localServiceAccountData, setLocalServiceAccountData] = useState(
    serviceAccountKeyData
  );
  const [localAppCredentialData, setLocalAppCredentialData] =
    useState(appCredentialData);
  const [
    localGoogleDrivePublicCredential,
    setLocalGoogleDrivePublicCredential,
  ] = useState(googleDrivePublicUploadedCredential);
  const [
    localGoogleDriveServiceAccountCredential,
    setLocalGoogleDriveServiceAccountCredential,
  ] = useState(googleDriveServiceAccountCredential);

  // Update local state when props change
  useEffect(() => {
    setLocalServiceAccountData(serviceAccountKeyData);
    setLocalAppCredentialData(appCredentialData);
    setLocalGoogleDrivePublicCredential(googleDrivePublicUploadedCredential);
    setLocalGoogleDriveServiceAccountCredential(
      googleDriveServiceAccountCredential
    );
  }, [
    serviceAccountKeyData,
    appCredentialData,
    googleDrivePublicUploadedCredential,
    googleDriveServiceAccountCredential,
  ]);

  const existingCredential =
    localGoogleDrivePublicCredential ||
    localGoogleDriveServiceAccountCredential;
  if (existingCredential) {
    return (
      <div>
        <div className="mt-4">
          <div className="py-3 px-4 bg-blue-50/30 dark:bg-blue-900/5 rounded mb-4 flex items-start">
            <FiCheck className="text-blue-500 h-5 w-5 mr-2 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <span className="font-medium block">{t("googleCredentials.authenticationComplete")}</span>
              <p className="text-sm mt-1 text-text-500 dark:text-text-400 break-words">
                {t("googleCredentials.driveAuthenticatedDesc")}
              </p>
            </div>
          </div>
          <Button
            danger
            onClick={async () => {
              handleRevokeAccess(
                connectorAssociated,
                existingCredential,
                refreshCredentials,
                t
              );
            }}
          >
          {t("googleCredentials.revokeAccess")}
          </Button>
        </div>
      </div>
    );
  }

  // If no credentials are uploaded, show message to complete step 1 first
  if (
    !localServiceAccountData?.service_account_email &&
    !localAppCredentialData?.client_id
  ) {
    return (
      <div>
        <SectionHeader>{t("googleCredentials.driveAuthentication")}</SectionHeader>
        <div className="mt-4">
          <div className="flex items-start py-3 px-4 bg-yellow-50/30 dark:bg-yellow-900/5 rounded">
            <FiAlertTriangle className="text-yellow-500 h-5 w-5 mr-2 mt-0.5 flex-shrink-0" />
            <p className="text-sm">
              {t("googleCredentials.completeStep1Drive")}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (localServiceAccountData?.service_account_email) {
    return (
      <div>
        <div className="mt-4">
          <Formik
            initialValues={{
              google_primary_admin: user?.email || "",
            }}
            validationSchema={Yup.object().shape({
              google_primary_admin: Yup.string()
                .email(t("googleCredentials.mustBeValidEmail"))
                .required(t("googleCredentials.required")),
            })}
            onSubmit={async (values, formikHelpers) => {
              formikHelpers.setSubmitting(true);
              try {
                const response = await fetch(
                  "/api/manage/admin/connector/google-drive/service-account-credential",
                  {
                    method: "PUT",
                    headers: {
                      "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                      google_primary_admin: values.google_primary_admin,
                    }),
                  }
                );

                if (response.ok) {
                  toast.success(
                    t("googleCredentials.createdServiceAccount")
                  );
                  refreshCredentials();
                } else {
                  const errorMsg = await response.text();
                  toast.error(
                    t("googleCredentials.failedCreateServiceAccount", { errorMsg })
                  );
                }
              } catch (error) {
                toast.error(
                  t("googleCredentials.failedCreateServiceAccount", { errorMsg: error })
                );
              } finally {
                formikHelpers.setSubmitting(false);
              }
            }}
          >
            {({ isSubmitting }) => (
              <Form>
                <TextFormField
                  name="google_primary_admin"
                  label={t("googleCredentials.primaryAdminEmail")}
                  subtext={t("googleCredentials.primaryAdminEmailDriveDesc")}
                />
                <div className="flex">
                  <Button type="submit" disabled={isSubmitting}>
                    {isSubmitting ? t("googleCredentials.creating") : t("googleCredentials.createCredential")}
                  </Button>
                </div>
              </Form>
            )}
          </Formik>
        </div>
      </div>
    );
  }

  if (localAppCredentialData?.client_id) {
    return (
      <div>
        <div className="bg-background-50/30 dark:bg-background-900/20 rounded mb-4">
          <p className="text-sm">
            {t("googleCredentials.driveOAuthDesc")}
          </p>
        </div>
        <Button
          disabled={isAuthenticating}
          onClick={async () => {
            setIsAuthenticating(true);
            try {
              // cookie used by callback to determine where to finally redirect to
              Cookies.set(GOOGLE_DRIVE_AUTH_IS_ADMIN_COOKIE_NAME, "true", {
                path: "/",
              });

              const [authUrl, errorMsg] = await setupGoogleDriveOAuth({
                isAdmin: true,
                name: "OAuth (uploaded)",
              });

              if (authUrl) {
                router.push(authUrl as Route);
              } else {
                toast.error(errorMsg);
                setIsAuthenticating(false);
              }
            } catch (error) {
              toast.error(
                t("googleCredentials.failedAuthDrive", { error })
              );
              setIsAuthenticating(false);
            }
          }}
        >
          {isAuthenticating
            ? t("googleCredentials.authenticating")
            : t("googleCredentials.authenticateWithDrive")}
        </Button>
      </div>
    );
  }

  // This code path should not be reached with the new conditions above
  return null;
};
