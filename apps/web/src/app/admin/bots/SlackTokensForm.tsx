"use client";

import { TextFormField } from "@/components/Field";
import { Form, Formik } from "formik";
import * as Yup from "yup";
import { createSlackBot, updateSlackBot } from "./new/lib";
import Button from "@/refresh-components/buttons/Button";
import Separator from "@/refresh-components/Separator";
import { useEffect } from "react";
import { DOCS_ADMINS_PATH } from "@/lib/constants";
import { toast } from "@/hooks/useToast";
import { useTranslation } from "react-i18next";

export const SlackTokensForm = ({
  isUpdate,
  initialValues,
  existingSlackBotId,
  refreshSlackBot,
  router,
  onValuesChange,
}: {
  isUpdate: boolean;
  initialValues: any;
  existingSlackBotId?: number;
  refreshSlackBot?: () => void;
  router: any;
  onValuesChange?: (values: any) => void;
}) => {
  const { t } = useTranslation();
  useEffect(() => {
    if (onValuesChange) {
      onValuesChange(initialValues);
    }
  }, [initialValues, onValuesChange]);

  return (
    <Formik
      initialValues={{
        ...initialValues,
      }}
      validationSchema={Yup.object().shape({
        bot_token: Yup.string().required(),
        app_token: Yup.string().required(),
        name: Yup.string().required(),
        user_token: Yup.string().optional(),
      })}
      onSubmit={async (values, formikHelpers) => {
        formikHelpers.setSubmitting(true);

        let response;
        if (isUpdate) {
          response = await updateSlackBot(existingSlackBotId!, values);
        } else {
          response = await createSlackBot(values);
        }
        formikHelpers.setSubmitting(false);
        if (response.ok) {
          if (refreshSlackBot) {
            refreshSlackBot();
          }
          const responseJson = await response.json();
          const botId = isUpdate ? existingSlackBotId : responseJson.id;
          toast.success(
            isUpdate
              ? t("admin.bots.successUpdated")
              : t("admin.bots.successCreated")
          );
          router.push(`/admin/bots/${encodeURIComponent(botId)}`);
        } else {
          const responseJson = await response.json();
          let errorMsg = responseJson.detail || responseJson.message;

          if (errorMsg.includes("Invalid bot token:")) {
            errorMsg = t("admin.bots.botTokenInvalid");
          } else if (errorMsg.includes("Invalid app token:")) {
            errorMsg = t("admin.bots.appTokenInvalid");
          }
          toast.error(
            isUpdate
              ? t("admin.bots.errorUpdating", { error: errorMsg })
              : t("admin.bots.errorCreating", { error: errorMsg })
          );
        }
      }}
      enableReinitialize={true}
    >
      {({ isSubmitting, setFieldValue, values }) => (
        <Form className="w-full">
          {!isUpdate && (
            <div className="">
              <TextFormField
                name="name"
                label={t("admin.bots.tokensFormNameLabel")}
                type="text"
              />
            </div>
          )}

          {!isUpdate && (
            <div className="mt-4">
              <Separator />
              {t("admin.bots.tokensFormGuidePrefix")}{" "}
              <a
                className="text-blue-500 hover:underline"
                href={`${DOCS_ADMINS_PATH}/getting_started/slack_bot_setup`}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("admin.bots.tokensFormGuideLink")}
              </a>{" "}
              {t("admin.bots.tokensFormGuideSuffix")}
            </div>
          )}
          <TextFormField
            name="bot_token"
            label={t("admin.bots.botTokenLabel")}
            type="password"
          />
          <TextFormField
            name="app_token"
            label={t("admin.bots.appTokenLabel")}
            type="password"
          />
          <TextFormField
            name="user_token"
            label={t("admin.bots.userTokenLabel")}
            type="password"
            subtext={t("admin.bots.userTokenSubtext")}
          />
          <div className="flex justify-end w-full mt-4">
            <Button
              type="submit"
              disabled={
                isSubmitting ||
                !values.bot_token ||
                !values.app_token ||
                !values.name
              }
            >
              {isUpdate ? t("admin.bots.updateButton") : t("admin.bots.createButton")}
            </Button>
          </div>
        </Form>
      )}
    </Formik>
  );
};
