"use client";

import { FeedbackType } from "@/app/app/interfaces";
import Button from "@/refresh-components/buttons/Button";
import useFeedbackController from "@/hooks/useFeedbackController";
import { useModal } from "@/refresh-components/contexts/ModalContext";
import { SvgThumbsDown, SvgThumbsUp } from "@opal/icons";
import Modal from "@/refresh-components/Modal";
import { Formik } from "formik";
import * as Yup from "yup";
import * as InputLayouts from "@/layouts/input-layouts";
import InputTextAreaField from "@/refresh-components/form/InputTextAreaField";
import { useTranslation } from "react-i18next";

export interface FeedbackModalProps {
  feedbackType: FeedbackType;
  messageId: number;
}

interface FeedbackFormValues {
  additional_feedback: string;
}

export default function FeedbackModal({
  feedbackType,
  messageId,
}: FeedbackModalProps) {
  const modal = useModal();
  const { t } = useTranslation();
  const { handleFeedbackChange } = useFeedbackController();

  const initialValues: FeedbackFormValues = {
    additional_feedback: "",
  };

  const validationSchema = Yup.object({
    additional_feedback:
      feedbackType === "dislike"
        ? Yup.string().trim().required(t("modals.feedback.required"))
        : Yup.string().trim(),
  });

  async function handleSubmit(values: FeedbackFormValues) {
    const feedbackText = values.additional_feedback;

    const success = await handleFeedbackChange(
      messageId,
      feedbackType,
      feedbackText,
      undefined
    );

    // Only close modal if submission was successful
    if (success) {
      modal.toggle(false);
    }
  }

  return (
    <>
      <Modal open={modal.isOpen} onOpenChange={modal.toggle}>
        <Modal.Content width="sm">
          <Modal.Header
            icon={feedbackType === "like" ? SvgThumbsUp : SvgThumbsDown}
            title={t("modals.feedback.title")}
            onClose={() => modal.toggle(false)}
          />
          <Formik
            initialValues={initialValues}
            validationSchema={validationSchema}
            onSubmit={handleSubmit}
          >
            {({
              isSubmitting,
              handleSubmit: formikHandleSubmit,
              dirty,
              isValid,
            }) => (
              <>
                <Modal.Body>
                  <InputLayouts.Vertical
                    name="additional_feedback"
                    title={t("modals.feedback.detailsLabel")}
                    optional={feedbackType === "like"}
                  >
                    <InputTextAreaField
                      name="additional_feedback"
                      placeholder={feedbackType === "like" ? t("modals.feedback.likePlaceholder") : t("modals.feedback.dislikePlaceholder")}
                    />
                  </InputLayouts.Vertical>
                </Modal.Body>

                <Modal.Footer>
                  <Button
                    onClick={() => modal.toggle(false)}
                    secondary
                    type="button"
                  >
                    {t("modals.cancel")}
                  </Button>
                  <Button
                    onClick={() => formikHandleSubmit()}
                    disabled={
                      isSubmitting ||
                      (feedbackType === "dislike" && (!dirty || !isValid))
                    }
                  >
                    {isSubmitting ? t("modals.feedback.submittingButton") : t("modals.feedback.submitButton")}
                  </Button>
                </Modal.Footer>
              </>
            )}
          </Formik>
        </Modal.Content>
      </Modal>
    </>
  );
}
