"use client";
import { use } from "react";

import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import Title from "@/components/ui/title";
import Separator from "@/refresh-components/Separator";
import { ChatSessionSnapshot, MessageSnapshot } from "../../usage/types";
import { FiBook } from "react-icons/fi";
import { timestampToReadableDate } from "@/lib/dateUtils";
import BackButton from "@/refresh-components/buttons/BackButton";
import { FeedbackBadge } from "../FeedbackBadge";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR from "swr";
import { ErrorCallout } from "@/components/ErrorCallout";
import FormSkeleton from "@/refresh-components/skeletons/FormSkeleton";
import CardSection from "@/components/admin/CardSection";

function MessageDisplay({ message }: { message: MessageSnapshot }) {
  const { t } = useTranslation("common", { keyPrefix: "admin" });
  return (
    <div>
      <Text as="p" className="text-xs font-bold mb-1">
        {message.message_type === "user"
          ? t("queryHistoryDetail.user")
          : t("queryHistoryDetail.ai")}
      </Text>
      <Text as="p" className="text-sm">
        {message.message}
      </Text>
      {message.documents.length > 0 && (
        <div className="flex flex-col gap-y-2 mt-2">
          <Text as="p" className="font-bold text-xs">
            {t("queryHistoryDetail.referenceDocuments")}
          </Text>
          {message.documents.slice(0, 5).map((document) => {
            return (
              <Text as="p" className="text-sm flex" key={document.document_id}>
                <FiBook
                  className={
                    "my-auto mr-1" + (document.link ? " text-link" : " ")
                  }
                />
                {document.link ? (
                  <a
                    href={document.link}
                    target="_blank"
                    className="text-link"
                    rel="noreferrer"
                  >
                    {document.semantic_identifier}
                  </a>
                ) : (
                  document.semantic_identifier
                )}
              </Text>
            );
          })}
        </div>
      )}
      {message.feedback_type && (
        <div className="mt-2">
          <Text as="p" className="font-bold text-xs">
            {t("queryHistoryDetail.feedback")}
          </Text>
          {message.feedback_text && (
            <Text as="p" className="text-sm">
              {message.feedback_text}
            </Text>
          )}
          <div className="mt-1">
            <FeedbackBadge feedback={message.feedback_type} />
          </div>
        </div>
      )}
      <Separator />
    </div>
  );
}

export default function QueryPage(props: { params: Promise<{ id: string }> }) {
  const { t } = useTranslation("common", { keyPrefix: "admin" });
  const params = use(props.params);
  const {
    data: chatSessionSnapshot,
    isLoading,
    error,
  } = useSWR<ChatSessionSnapshot>(
    `/api/admin/chat-session-history/${params.id}`,
    errorHandlingFetcher
  );

  if (isLoading) {
    return (
      <div className="p-6">
        <FormSkeleton fieldCount={4} />
      </div>
    );
  }

  if (!chatSessionSnapshot || error) {
    return (
      <ErrorCallout
        errorTitle={t("queryHistoryDetail.somethingWentWrong")}
        errorMsg={`Failed to fetch chat session - ${error}`}
      />
    );
  }

  return (
    <main className="pt-4 mx-auto container">
      <BackButton />

      <CardSection className="mt-4">
        <Title>{t("queryHistoryDetail.chatSessionDetails")}</Title>

        <Text
          as="p"
          className="text-sm flex flex-wrap whitespace-normal mt-1 text-sm"
        >
          {chatSessionSnapshot.assistant_name}
        </Text>
        <Text
          as="p"
          className="text-sm flex flex-wrap whitespace-normal mt-1 text-xs"
        >
          {chatSessionSnapshot.user_email &&
            `${chatSessionSnapshot.user_email}, `}
          {timestampToReadableDate(chatSessionSnapshot.time_created)},{" "}
          {chatSessionSnapshot.flow_type}
        </Text>

        <Separator />

        <div className="flex flex-col">
          {chatSessionSnapshot.messages.map((message) => {
            return <MessageDisplay key={message.id} message={message} />;
          })}
        </div>
      </CardSection>
    </main>
  );
}
