"use client";

import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgUserManage } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
import {
  ClarificationQuestion,
  PacketType,
  UserClarificationAnswered,
  UserClarificationPacket,
  UserClarificationRequest,
} from "../../../services/streamingModels";
import { MessageRenderer } from "../interfaces";

/** The packet version this renderer understands. A newer card is not drawn
 *  half-right: a question shown with the wrong controls would collect the
 *  wrong answer. */
const SUPPORTED_VERSION = 1;

/** The card always offers this, so the model never has to write it — and a
 *  user is never cornered by four options that all miss the point. An empty
 *  selection is what it sends, so nothing depends on matching a magic label. */
const DEFERRED: string[] = [];

function isAnswered(
  obj: UserClarificationRequest | UserClarificationAnswered
): obj is UserClarificationAnswered {
  return obj.type === PacketType.USER_CLARIFICATION_ANSWERED;
}

/**
 * An `ask_user` card: the agent could not tell what the user meant and asked
 * instead of guessing. The run is genuinely paused behind this card.
 *
 * Multiple questions become tabs. A single-choice answer advances to the next
 * tab on click, which halves the clicks; a multi-select waits for "Continue",
 * because the first click there does not mean the user is done. The whole set
 * is sent in one packet when the last tab is answered — a separate submit
 * step would just be one more thing to forget.
 *
 * The message box is never locked. Typing instead of answering is a first-class
 * way out (design K4): it resumes the run marked explicitly as "not an answer",
 * so nothing has to guess which question a stray sentence belonged to.
 */
export const UserClarificationRenderer: MessageRenderer<
  UserClarificationPacket,
  any
> = ({ packets, state, children }) => {
  const { t } = useTranslation();
  const [selections, setSelections] = useState<Record<string, string[]>>({});
  const [activeTab, setActiveTab] = useState(0);
  const [sent, setSent] = useState(false);

  const request = packets.find(
    (p) => p.obj.type === PacketType.USER_CLARIFICATION
  )?.obj as UserClarificationRequest | undefined;

  const answered = packets.map((p) => p.obj).find(isAnswered) as
    | UserClarificationAnswered
    | undefined;

  const questions: ClarificationQuestion[] = useMemo(
    () => (request?.questions ?? []).filter((q) => q && q.header),
    [request]
  );

  if (!request) {
    return children([{ icon: null, status: null, content: <></> }]);
  }

  if (request.v !== SUPPORTED_VERSION) {
    return children([
      {
        icon: null,
        status: null,
        timelineLayout: "content",
        content: (
          <div
            data-testid="user-clarification-unsupported"
            className="my-2 w-full rounded-lg border border-border-02 bg-background-tint-01 p-4"
          >
            <Text text03 secondaryBody>
              {t(
                "clarification.unsupported",
                "Bu soru bu sürümde gösterilemiyor. Ne yapmak istediğinizi yazarak devam edebilirsiniz."
              )}
            </Text>
          </div>
        ),
      },
    ]);
  }

  // Once answered the card is a record, not a control: a second answer would
  // be read as a brand new turn, so the buttons go away rather than lead there.
  const locked = sent || answered !== undefined || state?.isStreaming === true;
  // A reloaded card shows what was actually sent; a live one shows what has
  // been picked so far.
  const shown: Record<string, string[]> = answered?.answers ?? selections;

  const current = questions[activeTab];
  const agentPath = request.agent_path ?? [];

  function pick(question: ClarificationQuestion, label: string | null) {
    if (locked) return;
    const header = question.header;
    const next = { ...selections };

    if (label === null) {
      next[header] = DEFERRED;
    } else if (question.multiSelect) {
      const currentPicks = next[header] ?? [];
      next[header] = currentPicks.includes(label)
        ? currentPicks.filter((l) => l !== label)
        : [...currentPicks, label];
    } else {
      next[header] = [label];
    }
    setSelections(next);

    // A single choice is a finished answer, so move on; a multi-select is not.
    if (!question.multiSelect) advance(next);
  }

  function advance(next: Record<string, string[]>) {
    const remaining = questions.findIndex((q) => next[q.header] === undefined);
    if (remaining === -1) {
      send(next);
      return;
    }
    setActiveTab(remaining);
  }

  function send(next: Record<string, string[]>) {
    setSent(true);
    state?.onClarificationAnswer?.({
      answered: true,
      answers: next,
    });
  }

  const answeredCount = questions.filter(
    (q) => shown[q.header] !== undefined
  ).length;

  return children([
    {
      icon: null,
      status: null,
      timelineLayout: "content",
      content: (
        <div
          data-testid="user-clarification"
          className="my-2 flex w-full flex-col gap-3 rounded-lg border border-border-02 bg-background-tint-01 p-4"
        >
          <div className="flex items-start gap-2">
            <SvgUserManage className="mt-0.5 h-4 w-4 shrink-0 stroke-text-03" />
            <Text text03 secondaryBody>
              {agentPath.length > 1
                ? t("clarification.askingAgent", "{{agent}} soruyor", {
                    agent: agentPath[agentPath.length - 1],
                  })
                : t("clarification.asking", "Doğru anladığımdan emin olayım")}
            </Text>
          </div>

          {questions.length > 1 && (
            <div
              role="tablist"
              data-testid="user-clarification-tabs"
              className="flex flex-wrap items-center gap-1 border-b border-border-02 pb-2"
            >
              {questions.map((question, index) => (
                <button
                  key={question.header}
                  type="button"
                  // `aria-selected` belongs to the tab role, not to a bare
                  // button — without the role a screen reader announces the
                  // strip as unrelated buttons and loses "3 of 4".
                  role="tab"
                  data-testid={`user-clarification-tab-${question.header}`}
                  aria-selected={index === activeTab}
                  onClick={() => setActiveTab(index)}
                  className={`rounded px-2 py-1 text-sm ${
                    index === activeTab
                      ? "bg-background-tint-02 text-text-01"
                      : "text-text-03"
                  }`}
                >
                  {question.header}
                  {shown[question.header] !== undefined && " ✓"}
                </button>
              ))}
              <Text
                text03
                secondaryBody
                className="ml-auto"
                data-testid="user-clarification-progress"
              >
                {answeredCount}/{questions.length}
              </Text>
            </div>
          )}

          {current && (
            <div className="flex flex-col gap-2">
              <Text mainContentBody className="whitespace-pre-wrap">
                {current.question}
              </Text>

              <div className="flex flex-col gap-1">
                {(current.options ?? []).map((option) => {
                  const picked = (shown[current.header] ?? []).includes(
                    option.label
                  );
                  return (
                    <button
                      key={option.label}
                      type="button"
                      disabled={locked}
                      aria-pressed={picked}
                      data-testid={`user-clarification-option-${option.label}`}
                      onClick={() => pick(current, option.label)}
                      className={`flex flex-col gap-0.5 rounded border p-2 text-left ${
                        picked
                          ? "border-border-01 bg-background-tint-02"
                          : "border-border-02"
                      } ${
                        locked ? "opacity-60" : "hover:bg-background-tint-02"
                      }`}
                    >
                      <Text secondaryBody>{option.label}</Text>
                      {option.description && (
                        <Text text03 secondaryBody>
                          {option.description}
                        </Text>
                      )}
                    </button>
                  );
                })}

                {!locked && (
                  <button
                    type="button"
                    data-testid="user-clarification-defer"
                    onClick={() => pick(current, null)}
                    className="rounded border border-border-02 p-2 text-left hover:bg-background-tint-02"
                  >
                    <Text text03 secondaryBody>
                      {t("clarification.defer", "Sen karar ver")}
                    </Text>
                  </button>
                )}
              </div>

              {current.multiSelect && !locked && (
                <Button
                  data-testid="user-clarification-continue"
                  prominence="primary"
                  disabled={(selections[current.header] ?? []).length === 0}
                  onClick={() => advance(selections)}
                >
                  {t("clarification.continue", "Devam")}
                </Button>
              )}
            </div>
          )}

          {answered && answered.answered === false && (
            <Text text03 secondaryBody data-testid="user-clarification-skipped">
              {t(
                "clarification.skipped",
                "Soruları yanıtlamak yerine yazdınız."
              )}
            </Text>
          )}

          {!locked && (
            <Text text03 secondaryBody>
              {t(
                "clarification.typeInstead",
                "Yazmayı tercih ederseniz sorular atlanır ve yazdığınız metin doğrudan iletilir."
              )}
            </Text>
          )}
        </div>
      ),
    },
  ]);
};

export default UserClarificationRenderer;
