"use client";

import CardSection from "@/components/admin/CardSection";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { SlackTokensForm } from "./SlackTokensForm";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { SvgSlack } from "@opal/icons";
import { useTranslation } from "react-i18next";

export const NewSlackBotForm = () => {
  const { t } = useTranslation();
  const [formValues] = useState({
    name: "",
    enabled: true,
    bot_token: "",
    app_token: "",
    user_token: "",
  });
  const router = useRouter();

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={SvgSlack}
        title={t("admin.bots.newBotPageTitle")}
        description={t("admin.bots.newBotPageDescription", {
          defaultValue: "Connect a new Slack Bot application to ATLAS.",
        })}
        separator
      />
      <SettingsLayouts.Body>
        <CardSection>
          <div className="p-4">
            <SlackTokensForm
              isUpdate={false}
              initialValues={formValues}
              router={router}
            />
          </div>
        </CardSection>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
};
