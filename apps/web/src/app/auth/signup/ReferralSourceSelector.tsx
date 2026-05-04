"use client";

import { useState } from "react";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { Label } from "@/components/Field";
import { useTranslation } from "react-i18next";

interface ReferralSourceSelectorProps {
  defaultValue?: string;
}

export default function ReferralSourceSelector({
  defaultValue,
}: ReferralSourceSelectorProps) {
  const [referralSource, setReferralSource] = useState(defaultValue);
  const { t } = useTranslation();

  const referralOptions = [
    { value: "search", label: t("auth.referral.searchEngine") },
    { value: "friend", label: t("auth.referral.friend") },
    { value: "linkedin", label: t("auth.referral.linkedin") },
    { value: "twitter", label: t("auth.referral.twitter") },
    { value: "hackernews", label: t("auth.referral.hackernews") },
    { value: "reddit", label: t("auth.referral.reddit") },
    { value: "youtube", label: t("auth.referral.youtube") },
    { value: "podcast", label: t("auth.referral.podcast") },
    { value: "blog", label: t("auth.referral.blog") },
    { value: "ads", label: t("auth.referral.ads") },
    { value: "other", label: t("auth.referral.other") },
  ];

  const handleChange = (value: string) => {
    setReferralSource(value);
    const cookies = require("js-cookie");
    cookies.set("referral_source", value, {
      expires: 365,
      path: "/",
      sameSite: "strict",
    });
  };

  return (
    <div className="w-full gap-y-2 flex flex-col">
      <Label className="text-text-950" small={false}>
        {t("auth.howDidYouHear")}
      </Label>
      <InputSelect value={referralSource} onValueChange={handleChange}>
        <InputSelect.Trigger placeholder={t("auth.selectOption")} />

        <InputSelect.Content>
          {referralOptions.map((option) => (
            <InputSelect.Item key={option.value} value={option.value}>
              {option.label}
            </InputSelect.Item>
          ))}
        </InputSelect.Content>
      </InputSelect>
    </div>
  );
}
