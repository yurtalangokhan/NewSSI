import { Form, Formik } from "formik";
import * as Yup from "yup";
import { toast } from "@/hooks/useToast";
import { ConnectorStatus, User, UserGroup } from "@/lib/types";
import { TextFormField } from "@/components/Field";
import { createUserGroup } from "./lib";
import { UserEditor } from "./UserEditor";
import { ConnectorEditor } from "./ConnectorEditor";
import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import Separator from "@/refresh-components/Separator";
import Text from "@/refresh-components/texts/Text";
import { SvgUsers } from "@opal/icons";
import { useTranslation } from "react-i18next";
export interface UserGroupCreationFormProps {
  onClose: () => void;
  users: User[];
  ccPairs: ConnectorStatus<any, any>[];
  existingUserGroup?: UserGroup;
}

export default function UserGroupCreationForm({
  onClose,
  users,
  ccPairs,
  existingUserGroup,
}: UserGroupCreationFormProps) {
  const { t } = useTranslation();
  const isUpdate = existingUserGroup !== undefined;

  // Filter out ccPairs that aren't access_type "private"
  const privateCcPairs = ccPairs.filter(
    (ccPair) => ccPair.access_type === "private"
  );

  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content>
        <Modal.Header
          icon={SvgUsers}
          title={
            isUpdate
              ? t("admin.groups.updateTitle")
              : t("admin.groups.createTitle")
          }
          onClose={onClose}
        />
        <Modal.Body>
          <Separator />

          <Formik
            initialValues={{
              name: existingUserGroup ? existingUserGroup.name : "",
              user_ids: [] as string[],
              cc_pair_ids: [] as number[],
            }}
            validationSchema={Yup.object().shape({
              name: Yup.string().required(t("admin.groups.nameRequired")),
              user_ids: Yup.array().of(Yup.string().required()),
              cc_pair_ids: Yup.array().of(Yup.number().required()),
            })}
            onSubmit={async (values, formikHelpers) => {
              formikHelpers.setSubmitting(true);
              let response;
              response = await createUserGroup(values);
              formikHelpers.setSubmitting(false);
              if (response.ok) {
                toast.success(
                  isUpdate
                    ? t("admin.groups.updatedSuccess")
                    : t("admin.groups.createdSuccess")
                );
                onClose();
              } else {
                const responseJson = await response.json();
                const errorMsg = responseJson.detail || responseJson.message;
                toast.error(
                  isUpdate
                    ? t("admin.groups.updateFailed", { errorMsg })
                    : t("admin.groups.createFailed", { errorMsg })
                );
              }
            }}
          >
            {({ isSubmitting, values, setFieldValue }) => (
              <Form>
                <TextFormField
                  name="name"
                  label={t("admin.groups.nameLabel")}
                  placeholder={t("admin.groups.namePlaceholder")}
                  disabled={isUpdate}
                />

                <Separator />

                <Text as="p" className="font-medium">
                  {t("admin.groups.selectConnectorsTitle")}
                </Text>
                <Text as="p" text02>
                  {t("admin.groups.selectConnectorsDescription")}
                  visible to users in this group.
                </Text>

                <ConnectorEditor
                  allCCPairs={privateCcPairs}
                  selectedCCPairIds={values.cc_pair_ids}
                  setSetCCPairIds={(ccPairsIds) =>
                    setFieldValue("cc_pair_ids", ccPairsIds)
                  }
                />

                <Separator />

                <Text as="p" className="font-medium">
                  {t("admin.groups.selectUsersTitle")}
                </Text>
                <Text as="p" text02>
                  {t("admin.groups.selectUsersDescription")}
                  documents indexed by the selected connectors.
                </Text>
                <div className="mb-3 gap-2">
                  <UserEditor
                    selectedUserIds={values.user_ids}
                    setSelectedUserIds={(userIds) =>
                      setFieldValue("user_ids", userIds)
                    }
                    allUsers={users}
                    existingUsers={[]}
                  />
                </div>
                <div className="flex">
                  <Button
                    type="submit"
                    disabled={isSubmitting}
                    className="mx-auto w-64"
                  >
                    {isUpdate
                      ? t("admin.groups.updateSubmit")
                      : t("admin.groups.createSubmit")}
                  </Button>
                </div>
              </Form>
            )}
          </Formik>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
