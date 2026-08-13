"use client";

import { usePaidEnterpriseFeaturesEnabled } from "@/components/settings/usePaidEnterpriseFeaturesEnabled";
import React, { useState, useEffect } from "react";
import { FormikProps } from "formik";
import { useUserGroups } from "@/lib/hooks";
import { BooleanFormField } from "@/components/Field";
import { useUser } from "@/providers/UserProvider";
import { GroupsMultiSelect } from "./GroupsMultiSelect";
import { useTranslation } from "react-i18next";

export type IsPublicGroupSelectorFormType = {
  is_public: boolean;
  groups: number[];
};

// This should be included for all forms that require groups / public access
// to be set, and access to this / permissioning should be handled within this component itself.
export const IsPublicGroupSelector = <T extends IsPublicGroupSelectorFormType>({
  formikProps,
  objectName,
  publicToWhom = "Users",
  removeIndent = false,
  enforceGroupSelection = true,
  smallLabels = false,
}: {
  formikProps: FormikProps<T>;
  objectName: string;
  publicToWhom?: "Users" | "Curators";
  removeIndent?: boolean;
  enforceGroupSelection?: boolean;
  smallLabels?: boolean;
}) => {
  const { t } = useTranslation("common", {
    keyPrefix: "isPublicGroupSelector",
  });
  const { t: tCommon } = useTranslation();
  const isPaidEnterpriseFeaturesEnabled =
    usePaidEnterpriseFeaturesEnabled();
  const { user, isAdmin, isCurator } = useUser();
  const { data: userGroups, isLoading: userGroupsIsLoading } = useUserGroups();

  const [shouldHideContent, setShouldHideContent] = useState(false);
  const canManagePublicAccess = isAdmin || isCurator;

  useEffect(() => {
    if (user && userGroups && isPaidEnterpriseFeaturesEnabled) {
      if (!isAdmin && userGroups.length === 1) {
        setShouldHideContent(true);
        formikProps.setFieldValue("is_public", false);
        formikProps.setFieldValue("groups", [userGroups[0]!.id]);
      } else if (!isAdmin && userGroups.length === 0) {
        formikProps.setFieldValue("is_public", false);
      }
      if (
        userGroups.length === 1 &&
        userGroups[0] !== undefined &&
        !canManagePublicAccess
      ) {
        formikProps.setFieldValue("groups", [userGroups[0].id]);
        setShouldHideContent(true);
      } else if (formikProps.values.is_public) {
        formikProps.setFieldValue("groups", []);
        setShouldHideContent(false);
      } else {
        setShouldHideContent(false);
      }
    }
  }, [user, userGroups, isPaidEnterpriseFeaturesEnabled, canManagePublicAccess]);

  if (userGroupsIsLoading) {
    return <div>{tCommon("common.loading")}</div>;
  }
  if (!isPaidEnterpriseFeaturesEnabled) {
    return null;
  }

  let firstUserGroupName = "Unknown";
  if (userGroups) {
    const userGroup = userGroups[0];
    if (userGroup) {
      firstUserGroupName = userGroup.name;
    }
  }

  if (shouldHideContent && enforceGroupSelection) {
    return (
      <>
        {userGroups && (
          <div className="mb-1 font-medium text-base">
            {t("assignedToGroup", { objectName })}{" "}
            <b>{firstUserGroupName}</b>.
          </div>
        )}
      </>
    );
  }

  return (
    <div>
      {isAdmin && (
        <>
          <BooleanFormField
            name="is_public"
            removeIndent={removeIndent}
            small={smallLabels}
            label={
              publicToWhom === "Curators"
                ? t("makeCuratorAccessible", { objectName })
                : t("makePublic", { objectName })
            }
            disabled={!isAdmin}
            subtext={
              <span className="block mt-2 text-sm text-text-600 dark:text-neutral-400">
                {t("usableByAllPrefix", { objectName })}{" "}
                <b>{t("allPublicToWhom", { publicToWhom })}</b>.{" "}
                {t("usableByAllSuffix")} <b>{t("adminsLabel")}</b>{" "}
                {t("andLabel")} <b>{publicToWhom}</b>{" "}
                {t("accessDescriptionSuffix", { objectName })}
              </span>
            }
          />
        </>
      )}

      <GroupsMultiSelect
        formikProps={formikProps}
        label={t("assignGroupAccessLabel", { objectName })}
        subtext={
          isAdmin || !enforceGroupSelection
            ? t("visibleByGroupsSubtext", { objectName })
            : t("curatorsMustSelectSubtext", { objectName })
        }
        disabled={formikProps.values.is_public && !isAdmin}
        disabledMessage={t("publicDisabledMessage", { objectName })}
      />
    </div>
  );
};
