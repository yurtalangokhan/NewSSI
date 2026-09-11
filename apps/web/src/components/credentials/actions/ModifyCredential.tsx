import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { Badge } from "@/components/ui/badge";
import { AccessType } from "@/lib/types";
import { EditIcon, NewChatIcon, SwapIcon } from "@/components/icons/icons";
import {
  ConfluenceCredentialJson,
  Credential,
} from "@/lib/connectors/credentials";
import { Connector } from "@/lib/connectors/connectors";
import { SvgAlertTriangle, SvgTrash } from "@opal/icons";
import { Button as OpalButton } from "@opal/components";
interface CredentialSelectionTableProps {
  credentials: Credential<any>[];
  editableCredentials: Credential<any>[];
  onSelectCredential: (credential: Credential<any> | null) => void;
  currentCredentialId?: number;
  onDeleteCredential: (credential: Credential<any>) => void;
  onEditCredential?: (credential: Credential<any>) => void;
}

function CredentialSelectionTable({
  credentials,
  editableCredentials,
  onEditCredential,
  onSelectCredential,
  currentCredentialId,
  onDeleteCredential,
}: CredentialSelectionTableProps) {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.modifyCredential",
  });
  const [selectedCredentialId, setSelectedCredentialId] = useState<
    number | null
  >(null);

  // rkuo: this appears to merge editableCredentials into credentials so we get a single list
  // of credentials to display
  // Pretty sure this merging should be done outside of this UI component
  const allCredentials = React.useMemo(() => {
    const credMap = new Map(editableCredentials.map((cred) => [cred.id, cred]));
    credentials.forEach((cred) => {
      if (!credMap.has(cred.id)) {
        credMap.set(cred.id, cred);
      }
    });
    return Array.from(credMap.values());
  }, [credentials, editableCredentials]);

  const handleSelectCredential = (credentialId: number) => {
    const newSelectedId =
      selectedCredentialId === credentialId ? null : credentialId;
    setSelectedCredentialId(newSelectedId);

    const selectedCredential =
      allCredentials.find((cred) => cred.id === newSelectedId) || null;
    onSelectCredential(selectedCredential);
  };

  return (
    <div className="w-full max-h-[50vh] overflow-auto">
      <table className="w-full text-sm border-collapse">
        <thead className="sticky top-0 w-full">
          <tr className="bg-neutral-100 dark:bg-neutral-900">
            <th className="p-2 text-left font-medium text-neutral-600 dark:text-neutral-400"></th>
            <th className="p-2 text-left font-medium text-neutral-600 dark:text-neutral-400">
              {t("idHeader")}
            </th>
            <th className="p-2 text-left font-medium text-neutral-600 dark:text-neutral-400">
              {t("nameHeader")}
            </th>
            <th className="p-2 text-left font-medium text-neutral-600 dark:text-neutral-400">
              {t("createdHeader")}
            </th>
            <th className="p-2 text-left font-medium text-neutral-600 dark:text-neutral-400">
              {t("lastUpdatedHeader")}
            </th>
            <th />
          </tr>
        </thead>

        {allCredentials.length > 0 && (
          <tbody className="w-full">
            {allCredentials.map((credential, ind) => {
              const selected = currentCredentialId
                ? credential.id == (selectedCredentialId || currentCredentialId)
                : false;
              const editable = editableCredentials.some(
                (editableCredential) => editableCredential.id === credential.id
              );
              return (
                <tr
                  key={credential.id}
                  className="border-b hover:bg-background-50"
                >
                  <td className="min-w-[60px] p-2">
                    {!selected ? (
                      <input
                        type="radio"
                        name="credentialSelection"
                        onChange={() => handleSelectCredential(credential.id)}
                        className="form-radio ml-4 h-4 w-4 text-blue-600 transition duration-150 ease-in-out"
                      />
                    ) : (
                      <Badge>{t("selectedBadge")}</Badge>
                    )}
                  </td>
                  <td className="p-2">{credential.id}</td>
                  <td className="p-2">
                    <Text as="p">
                      {credential.name ?? t("untitledFallback")}
                    </Text>
                  </td>
                  <td className="p-2">
                    {new Date(credential.time_created).toLocaleString()}
                  </td>
                  <td className="p-2">
                    {new Date(credential.time_updated).toLocaleString()}
                  </td>
                  <td className="p-2 flex gap-x-2 content-center mt-auto">
                    <OpalButton
                      onClick={async () => {
                        onDeleteCredential(credential);
                      }}
                      disabled={selected || !editable}
                      icon={SvgTrash}
                    />
                    {onEditCredential && (
                      <button
                        disabled={!editable}
                        onClick={() => onEditCredential(credential)}
                        className="cursor-pointer my-auto"
                      >
                        <EditIcon />
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        )}
      </table>

      {allCredentials.length == 0 && (
        <Text as="p" className="mt-4">
          {" "}
          {t("noCredentialsMessage")}
        </Text>
      )}
    </div>
  );
}

export interface ModifyCredentialProps {
  close?: () => void;
  showIfEmpty?: boolean;
  attachedConnector?: Connector<any>;
  credentials: Credential<any>[];
  editableCredentials: Credential<any>[];
  defaultedCredential?: Credential<any>;
  accessType: AccessType;
  onSwap?: (
    newCredential: Credential<any>,
    connectorId: number,
    accessType: AccessType
  ) => void;
  onSwitch?: (newCredential: Credential<any>) => void;
  onEditCredential?: (credential: Credential<ConfluenceCredentialJson>) => void;
  onDeleteCredential: (credential: Credential<any | null>) => void;
  onCreateNew?: () => void;
}

export default function ModifyCredential({
  close,
  showIfEmpty,
  attachedConnector,
  credentials,
  editableCredentials,
  defaultedCredential,
  accessType,
  onSwap,
  onSwitch,
  onEditCredential,
  onDeleteCredential,
  onCreateNew,
}: ModifyCredentialProps) {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.modifyCredential",
  });
  const [selectedCredential, setSelectedCredential] =
    useState<Credential<any> | null>(null);
  const [confirmDeletionCredential, setConfirmDeletionCredential] =
    useState<null | Credential<any>>(null);

  if (!credentials || !editableCredentials) return null;

  return (
    <>
      {confirmDeletionCredential != null && (
        <Modal open onOpenChange={() => setConfirmDeletionCredential(null)}>
          <Modal.Content width="sm" height="sm">
            <Modal.Header
              icon={SvgAlertTriangle}
              title={t("confirmDeletionTitle")}
              onClose={() => setConfirmDeletionCredential(null)}
            />
            <Modal.Body>
              <Text as="p">{t("confirmDeletionBody")}</Text>
            </Modal.Body>
            <Modal.Footer>
              <Button
                onClick={async () => {
                  onDeleteCredential(confirmDeletionCredential);
                  setConfirmDeletionCredential(null);
                }}
              >
                {t("confirmButton")}
              </Button>
              <Button
                secondary
                onClick={() => setConfirmDeletionCredential(null)}
              >
                {t("cancelButton")}
              </Button>
            </Modal.Footer>
          </Modal.Content>
        </Modal>
      )}

      <div className="mb-0">
        <Text as="p" className="mb-4">
          {t("selectCredentialHint")}
        </Text>

        <CredentialSelectionTable
          onDeleteCredential={async (credential: Credential<any | null>) => {
            setConfirmDeletionCredential(credential);
          }}
          onEditCredential={
            onEditCredential
              ? (credential: Credential<ConfluenceCredentialJson>) =>
                  onEditCredential(credential)
              : undefined
          }
          currentCredentialId={
            defaultedCredential ? defaultedCredential.id : undefined
          }
          credentials={credentials}
          editableCredentials={editableCredentials}
          onSelectCredential={(credential: Credential<any> | null) => {
            if (credential && onSwitch) {
              onSwitch(credential);
            } else {
              setSelectedCredential(credential);
            }
          }}
        />

        {!showIfEmpty && (
          <div className="flex mt-8 justify-between">
            {onCreateNew ? (
              <Button
                onClick={() => {
                  onCreateNew();
                }}
                className="bg-background-500 disabled:border-transparent
              transition-colors duration-150 ease-in disabled:bg-background-300
              disabled:hover:bg-background-300 hover:bg-background-600 cursor-pointer"
              >
                <div className="flex gap-x-2 items-center w-full border-none">
                  <NewChatIcon className="text-white" />
                  <Text as="p">{t("createButton")}</Text>
                </div>
              </Button>
            ) : (
              <div />
            )}

            <Button
              disabled={selectedCredential == null}
              onClick={() => {
                if (onSwap && attachedConnector) {
                  onSwap(selectedCredential!, attachedConnector.id, accessType);
                  if (close) {
                    close();
                  }
                }
                if (onSwitch) {
                  onSwitch(selectedCredential!);
                }
              }}
              className="bg-indigo-500 disabled:border-transparent
              transition-colors duration-150 ease-in disabled:bg-indigo-300
              disabled:hover:bg-indigo-300 hover:bg-indigo-600 cursor-pointer"
            >
              <div className="flex gap-x-2 items-center w-full border-none">
                <SwapIcon className="text-white" />
                <Text as="p">{t("selectButton")}</Text>
              </div>
            </Button>
          </div>
        )}
      </div>
    </>
  );
}
