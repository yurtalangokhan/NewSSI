"use client";

import * as Yup from "yup";
import Button from "@/refresh-components/buttons/Button";
import { useEffect, useState } from "react";
import Modal from "@/refresh-components/Modal";
import { Form, Formik } from "formik";
import { SelectorFormField, TextFormField } from "@/components/Field";
import { UserGroup } from "@/lib/types";
import { Scope } from "./types";
import { toast } from "@/hooks/useToast";
import { SvgSettings } from "@opal/icons";
import { useTranslation } from "react-i18next";
interface CreateRateLimitModalProps {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
  onSubmit: (
    target_scope: Scope,
    period_hours: number,
    token_budget: number,
    group_id: number
  ) => void;
  forSpecificScope?: Scope;
  forSpecificUserGroup?: number;
}

export default function CreateRateLimitModal({
  isOpen,
  setIsOpen,
  onSubmit,
  forSpecificScope,
  forSpecificUserGroup,
}: CreateRateLimitModalProps) {
  const { t } = useTranslation();
  const [modalUserGroups, setModalUserGroups] = useState([]);
  const [shouldFetchUserGroups, setShouldFetchUserGroups] = useState(
    forSpecificScope === Scope.USER_GROUP
  );

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch("/api/manage/admin/user-group");
        const data = await response.json();
        const options = data.map((userGroup: UserGroup) => ({
          name: userGroup.name,
          value: userGroup.id,
        }));
        setModalUserGroups(options);
        setShouldFetchUserGroups(false);
      } catch (error) {
        toast.error(t("admin.tokenRateLimits.fetchUserGroupsError", { error }));
      }
    };

    if (shouldFetchUserGroups) {
      fetchData();
    }
  }, [shouldFetchUserGroups]);

  return (
    <Modal open={isOpen} onOpenChange={() => setIsOpen(false)}>
      <Modal.Content width="sm" height="sm">
        <Modal.Header
          icon={SvgSettings}
          title={t("admin.tokenRateLimits.createModalTitle")}
          onClose={() => setIsOpen(false)}
        />
        <Modal.Body>
          <Formik
            initialValues={{
              enabled: true,
              period_hours: "",
              token_budget: "",
              target_scope: forSpecificScope || Scope.GLOBAL,
              user_group_id: forSpecificUserGroup,
            }}
            validationSchema={Yup.object().shape({
              period_hours: Yup.number()
                .required(t("admin.tokenRateLimits.timeWindowRequired"))
                .min(1, t("admin.tokenRateLimits.timeWindowMin")),
              token_budget: Yup.number()
                .required(t("admin.tokenRateLimits.tokenBudgetRequired"))
                .min(1, t("admin.tokenRateLimits.tokenBudgetMin")),
              target_scope: Yup.string().required(
                t("admin.tokenRateLimits.targetScopeRequired")
              ),
              user_group_id: Yup.string().test(
                "user_group_id",
                t("admin.tokenRateLimits.userGroupRequired"),
                (value, context) => {
                  return (
                    context.parent.target_scope !== "user_group" ||
                    (context.parent.target_scope === "user_group" &&
                      value !== undefined)
                  );
                }
              ),
            })}
            onSubmit={async (values, formikHelpers) => {
              formikHelpers.setSubmitting(true);
              onSubmit(
                values.target_scope,
                Number(values.period_hours),
                Number(values.token_budget),
                Number(values.user_group_id)
              );
              return formikHelpers.setSubmitting(false);
            }}
          >
            {({ isSubmitting, values, setFieldValue }) => (
              <Form className="overflow-visible px-2">
                {!forSpecificScope && (
                  <SelectorFormField
                    name="target_scope"
                    label={t("admin.tokenRateLimits.targetScopeLabel")}
                    options={[
                      { name: t("admin.tokenRateLimits.scopeGlobal"), value: Scope.GLOBAL },
                      { name: t("admin.tokenRateLimits.scopeUser"), value: Scope.USER },
                      { name: t("admin.tokenRateLimits.scopeUserGroup"), value: Scope.USER_GROUP },
                    ]}
                    includeDefault={false}
                    onSelect={(selected) => {
                      setFieldValue("target_scope", selected);
                      if (selected === Scope.USER_GROUP) {
                        setShouldFetchUserGroups(true);
                      }
                    }}
                  />
                )}
                {forSpecificUserGroup === undefined &&
                  values.target_scope === Scope.USER_GROUP && (
                    <SelectorFormField
                      name="user_group_id"
                      label={t("admin.tokenRateLimits.userGroupLabel")}
                      options={modalUserGroups}
                      includeDefault={false}
                    />
                  )}
                <TextFormField
                  name="period_hours"
                  label={t("admin.tokenRateLimits.timeWindowLabel")}
                  type="number"
                  placeholder=""
                />
                <TextFormField
                  name="token_budget"
                  label={t("admin.tokenRateLimits.tokenBudgetLabel")}
                  type="number"
                  placeholder=""
                />
                <Button type="submit" disabled={isSubmitting}>
                  {t("admin.tokenRateLimits.createSubmitButton")}
                </Button>
              </Form>
            )}
          </Formik>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
