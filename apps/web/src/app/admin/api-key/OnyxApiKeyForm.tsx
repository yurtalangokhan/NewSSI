import { Form, Formik } from "formik";
import { toast } from "@/hooks/useToast";
import { createApiKey, updateApiKey } from "./lib";
import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputComboBox from "@/refresh-components/inputs/InputComboBox";
import { FormikField } from "@/refresh-components/form/FormikField";
import { FormField } from "@/refresh-components/form/FormField";
import { USER_ROLE_LABELS, UserRole } from "@/lib/types";
import { APIKey } from "./types";
import { SvgKey } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface OnyxApiKeyFormProps {
  onClose: () => void;
  onCreateApiKey: (apiKey: APIKey) => void;
  apiKey?: APIKey;
}

export default function OnyxApiKeyForm({
  onClose,
  onCreateApiKey,
  apiKey,
}: OnyxApiKeyFormProps) {
  const { t } = useTranslation();
  const isUpdate = apiKey !== undefined;

  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content width="sm" height="lg">
        <Modal.Header
          icon={SvgKey}
          title={isUpdate ? t("admin.apiKey.updateTitle") : t("admin.apiKey.createTitle")}
          onClose={onClose}
        />
        <Formik
          initialValues={{
            name: apiKey?.api_key_name || "",
            role: apiKey?.api_key_role || UserRole.BASIC.toString(),
          }}
          onSubmit={async (values, formikHelpers) => {
            formikHelpers.setSubmitting(true);

            const payload = {
              ...values,
              role: values.role as UserRole,
            };

            let response;
            if (isUpdate) {
              response = await updateApiKey(apiKey.api_key_id, payload);
            } else {
              response = await createApiKey(payload);
            }
            formikHelpers.setSubmitting(false);
            if (response.ok) {
              toast.success(
                isUpdate
                  ? t("admin.apiKey.successUpdated")
                  : t("admin.apiKey.successCreated")
              );
              if (!isUpdate) {
                onCreateApiKey(await response.json());
              }
              onClose();
            } else {
              const responseJson = await response.json();
              const errorMsg = responseJson.detail || responseJson.message;
              toast.error(
                isUpdate
                  ? t("admin.apiKey.errorUpdating", { errorMsg })
                  : t("admin.apiKey.errorCreating", { errorMsg })
              );
            }
          }}
        >
          {({ isSubmitting }) => (
            <Form className="w-full overflow-visible">
              <Modal.Body>
                <Text as="p">{t("admin.apiKey.nameHint")}</Text>

                <FormikField<string>
                  name="name"
                  render={(field, helper, _meta, state) => (
                    <FormField name="name" state={state} className="w-full">
                      <FormField.Label>{t("admin.apiKey.nameLabel")}</FormField.Label>
                      <FormField.Control>
                        <InputTypeIn
                          {...field}
                          placeholder=""
                          onClear={() => helper.setValue("")}
                          showClearButton={false}
                        />
                      </FormField.Control>
                    </FormField>
                  )}
                />

                <FormikField<string>
                  name="role"
                  render={(field, helper, _meta, state) => (
                    <FormField name="role" state={state} className="w-full">
                      <FormField.Label>{t("admin.apiKey.roleLabel")}</FormField.Label>
                      <FormField.Control>
                        <InputComboBox
                          value={field.value}
                          onValueChange={(value) => helper.setValue(value)}
                          options={[
                            {
                              label: USER_ROLE_LABELS[UserRole.LIMITED],
                              value: UserRole.LIMITED.toString(),
                            },
                            {
                              label: USER_ROLE_LABELS[UserRole.BASIC],
                              value: UserRole.BASIC.toString(),
                            },
                            {
                              label: USER_ROLE_LABELS[UserRole.ADMIN],
                              value: UserRole.ADMIN.toString(),
                            },
                          ]}
                          placeholder={t("admin.apiKey.roleSelectPlaceholder")}
                          strict
                        />
                      </FormField.Control>
                      <FormField.Description>
                        {t("admin.apiKey.roleDescription")}
                      </FormField.Description>
                    </FormField>
                  )}
                />
              </Modal.Body>

              <Modal.Footer>
                <Button type="submit" disabled={isSubmitting}>
                  {isUpdate ? t("admin.apiKey.updateSubmitButton") : t("admin.apiKey.createSubmitButton")}
                </Button>
              </Modal.Footer>
            </Form>
          )}
        </Formik>
      </Modal.Content>
    </Modal>
  );
}
