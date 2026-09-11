"use client";

import { authenticatedFetch } from "@/lib/fetcher";

import { withFormik, FormikProps, FormikErrors, Form } from "formik";
import Button from "@/refresh-components/buttons/Button";
import InputTextAreaField from "@/refresh-components/form/InputTextAreaField";
import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n/config";

const WHITESPACE_SPLIT = /\s+/;
const EMAIL_REGEX = /[^@]+@[^.]+\.[^.]/;

const addUsers = async (url: string, { arg }: { arg: Array<string> }) => {
  return await authenticatedFetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ emails: arg }),
  });
};

export type EmailInviteStatus =
  | "SENT"
  | "NOT_CONFIGURED"
  | "SEND_FAILED"
  | "DISABLED";

interface FormProps {
  onSuccess: (emailInviteStatus: EmailInviteStatus) => void;
  onFailure: (res: Response) => void;
}

interface FormValues {
  emails: string;
}

const normalizeEmails = (emails: string) =>
  emails
    .trim()
    .split(WHITESPACE_SPLIT)
    .filter(Boolean)
    .map((email) => email.toLowerCase());

const AddUserFormRenderer = ({
  touched,
  errors,
  isSubmitting,
  handleSubmit,
}: FormikProps<FormValues>) => {
  const { t } = useTranslation();
  return (
    <Form className="w-full" onSubmit={handleSubmit}>
      <InputTextAreaField
        id="emails"
        name="emails"
        className="w-full"
        autoResize
        maxRows={8}
        onKeyDown={(e: React.KeyboardEvent<HTMLTextAreaElement>) => {
          if (e.key === "Enter") {
            e.preventDefault();
            handleSubmit();
          }
        }}
      />
      {touched.emails && errors.emails && (
        <Text as="p" secondaryBody className="text-error">
          {errors.emails}
        </Text>
      )}
      <Button type="submit" disabled={isSubmitting} className="self-end">
        {t("admin.users.addButton")}
      </Button>
    </Form>
  );
};

const AddUserForm = withFormik<FormProps, FormValues>({
  mapPropsToValues: (props) => {
    return {
      emails: "",
    };
  },
  validate: (values: FormValues): FormikErrors<FormValues> => {
    const emails = normalizeEmails(values.emails);
    if (!emails.length) {
      return { emails: i18n.t("admin.users.emailRequired") };
    }
    for (let email of emails) {
      if (!email.match(EMAIL_REGEX)) {
        return { emails: i18n.t("admin.users.invalidEmailError", { email }) };
      }
    }
    return {};
  },
  handleSubmit: async (values: FormValues, formikBag) => {
    const emails = normalizeEmails(values.emails);
    formikBag.setSubmitting(true);
    await addUsers("/api/user-service/users/invite", { arg: emails })
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          formikBag.props.onSuccess(data.email_invite_status);
        } else {
          formikBag.props.onFailure(res);
        }
      })
      .finally(() => {
        formikBag.setSubmitting(false);
      });
  },
})(AddUserFormRenderer);

const BulkAdd = ({ onSuccess, onFailure }: FormProps) => {
  return <AddUserForm onSuccess={onSuccess} onFailure={onFailure} />;
};

export default BulkAdd;
