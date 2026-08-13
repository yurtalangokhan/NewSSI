"use client";

import { toast } from "@/hooks/useToast";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ConnectorTitle } from "@/components/admin/connectors/ConnectorTitle";
import AddMemberForm from "./AddMemberForm";
import { updateUserGroup } from "./lib";
import { LoadingAnimation } from "@/components/Loading";
import { User, UserGroup, ConnectorStatus } from "@/lib/types";
import AddConnectorForm from "./AddConnectorForm";
import Separator from "@/refresh-components/Separator";
import Text from "@/components/ui/text";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import Button from "@/refresh-components/buttons/Button";
import { DeleteButton } from "@/components/DeleteButton";
import { Bubble } from "@/components/Bubble";
import { BookmarkIcon, RobotIcon } from "@/components/icons/icons";
import { AddTokenRateLimitForm } from "./AddTokenRateLimitForm";
import { GenericTokenRateLimitTable } from "@/app/admin/token-rate-limits/TokenRateLimitTables";
import { useUser } from "@/providers/UserProvider";
import { formatRoleName } from "@/lib/auth/roles";

interface GroupDisplayProps {
  users: User[];
  ccPairs: ConnectorStatus<any, any>[];
  userGroup: UserGroup;
  refreshUserGroup: () => void;
}

const UserRoleDropdown = ({ user }: { user: User }) => {
  const { t } = useTranslation();
  return (
    <div>
      {t(`admin.users.roles.${user.role}`, {
        defaultValue: formatRoleName(user.role),
      })}
    </div>
  );
};

export const GroupDisplay = ({
  users,
  ccPairs,
  userGroup,
  refreshUserGroup,
}: GroupDisplayProps) => {
  const { t } = useTranslation();
  const [addMemberFormVisible, setAddMemberFormVisible] = useState(false);
  const [addConnectorFormVisible, setAddConnectorFormVisible] = useState(false);
  const [addRateLimitFormVisible, setAddRateLimitFormVisible] = useState(false);

  const { isAdmin } = useUser();

  return (
    <div>
      <div className="text-sm mb-3 flex">
        <Text className="mr-1">{t("admin.groups.statusLabel")}</Text>{" "}
        {userGroup.is_up_to_date ? (
          <div className="text-success font-bold">
            {t("admin.groups.upToDate")}
          </div>
        ) : (
          <div className="text-accent font-bold">
            <LoadingAnimation text={t("admin.groups.syncing")} />
          </div>
        )}
      </div>

      <Separator />

      <div className="flex w-full">
        <h2 className="text-xl font-bold">{t("admin.groups.usersSection")}</h2>
      </div>

      <div className="mt-2">
        {userGroup.users.length > 0 ? (
          <>
            <Table className="overflow-visible">
              <TableHeader>
                <TableRow>
                  <TableHead>{t("admin.groups.emailHeader")}</TableHead>
                  <TableHead>{t("admin.groups.roleHeader")}</TableHead>
                  <TableHead className="flex w-full">
                    <div className="ml-auto">
                      {t("admin.groups.removeUserHeader")}
                    </div>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {userGroup.users.map((groupMember) => {
                  return (
                    <TableRow key={groupMember.id}>
                      <TableCell className="whitespace-normal break-all">
                        {groupMember.email}
                      </TableCell>
                      <TableCell>
                        <UserRoleDropdown user={groupMember} />
                      </TableCell>
                      <TableCell>
                        <div className="flex w-full">
                          <div className="ml-auto m-2">
                            {(isAdmin ||
                              !userGroup.curator_ids.includes(
                                groupMember.id
                              )) && (
                              <DeleteButton
                                onClick={async () => {
                                  const response = await updateUserGroup(
                                    userGroup.id,
                                    {
                                      user_ids: userGroup.users
                                        .filter(
                                          (userGroupUser) =>
                                            userGroupUser.id !== groupMember.id
                                        )
                                        .map(
                                          (userGroupUser) => userGroupUser.id
                                        ),
                                      cc_pair_ids: userGroup.cc_pairs.map(
                                        (ccPair) => ccPair.id
                                      ),
                                    }
                                  );
                                  if (response.ok) {
                                    toast.success(
                                      t("admin.groups.removedUserSuccess")
                                    );
                                  } else {
                                    const responseJson = await response.json();
                                    const errorMsg =
                                      responseJson.detail ||
                                      responseJson.message;
                                    toast.error(
                                      t("admin.groups.removeUserFailed", {
                                        errorMsg,
                                      })
                                    );
                                  }
                                  refreshUserGroup();
                                }}
                              />
                            )}
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </>
        ) : (
          <div className="text-sm">{t("admin.groups.noUsers")}</div>
        )}
      </div>

      <SimpleTooltip
        tooltip={t("admin.groups.syncTooltip")}
        disabled={userGroup.is_up_to_date}
      >
        <Button
          disabled={!userGroup.is_up_to_date}
          onClick={() => {
            if (userGroup.is_up_to_date) {
              setAddMemberFormVisible(true);
            }
          }}
        >
          {t("admin.groups.addUsersButton")}
        </Button>
      </SimpleTooltip>
      {addMemberFormVisible && (
        <AddMemberForm
          users={users}
          userGroup={userGroup}
          onClose={() => {
            setAddMemberFormVisible(false);
            refreshUserGroup();
          }}
        />
      )}

      <Separator />

      <h2 className="text-xl font-bold mt-8">
        {t("admin.groups.connectorsSection")}
      </h2>
      <div className="mt-2">
        {userGroup.cc_pairs.length > 0 ? (
          <>
            <Table className="overflow-visible">
              <TableHeader>
                <TableRow>
                  <TableHead>{t("admin.groups.connectorHeader")}</TableHead>
                  <TableHead className="flex w-full">
                    <div className="ml-auto">
                      {t("admin.groups.removeConnectorHeader")}
                    </div>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {userGroup.cc_pairs.map((ccPair) => {
                  return (
                    <TableRow key={ccPair.id}>
                      <TableCell className="whitespace-normal break-all">
                        <ConnectorTitle
                          connector={ccPair.connector}
                          ccPairId={ccPair.id}
                          ccPairName={ccPair.name}
                        />
                      </TableCell>
                      <TableCell>
                        <div className="flex w-full">
                          <div className="ml-auto m-2">
                            <DeleteButton
                              onClick={async () => {
                                const response = await updateUserGroup(
                                  userGroup.id,
                                  {
                                    user_ids: userGroup.users.map(
                                      (userGroupUser) => userGroupUser.id
                                    ),
                                    cc_pair_ids: userGroup.cc_pairs
                                      .filter(
                                        (userGroupCCPair) =>
                                          userGroupCCPair.id != ccPair.id
                                      )
                                      .map((ccPair) => ccPair.id),
                                  }
                                );
                                if (response.ok) {
                                  toast.success(
                                    t("admin.groups.removedConnectorSuccess")
                                  );
                                } else {
                                  const responseJson = await response.json();
                                  const errorMsg =
                                    responseJson.detail || responseJson.message;
                                  toast.error(
                                    t("admin.groups.removeConnectorFailed", {
                                      errorMsg,
                                    })
                                  );
                                }
                                refreshUserGroup();
                              }}
                            />
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </>
        ) : (
          <div className="text-sm">{t("admin.groups.noConnectors")}</div>
        )}
      </div>

      <SimpleTooltip
        tooltip={t("admin.groups.syncTooltip")}
        disabled={userGroup.is_up_to_date}
      >
        <Button
          disabled={!userGroup.is_up_to_date}
          onClick={() => {
            if (userGroup.is_up_to_date) {
              setAddConnectorFormVisible(true);
            }
          }}
        >
          {t("admin.groups.addConnectorsButton")}
        </Button>
      </SimpleTooltip>

      {addConnectorFormVisible && (
        <AddConnectorForm
          ccPairs={ccPairs}
          userGroup={userGroup}
          onClose={() => {
            setAddConnectorFormVisible(false);
            refreshUserGroup();
          }}
        />
      )}

      <Separator />

      <h2 className="text-xl font-bold mt-8 mb-2">
        {t("admin.groups.documentSetsSection")}
      </h2>

      <div>
        {userGroup.document_sets.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {userGroup.document_sets.map((documentSet) => {
              return (
                <Bubble isSelected key={documentSet.id}>
                  <div className="flex">
                    <BookmarkIcon />
                    <Text className="ml-1">{documentSet.name}</Text>
                  </div>
                </Bubble>
              );
            })}
          </div>
        ) : (
          <>
            <Text>{t("admin.groups.noDocumentSets")}</Text>
          </>
        )}
      </div>

      <Separator />

      <h2 className="text-xl font-bold mt-8 mb-2">
        {t("admin.groups.agentsSection")}
      </h2>

      <div>
        {userGroup.document_sets.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {userGroup.personas.map((persona) => {
              return (
                <Bubble isSelected key={persona.id}>
                  <div className="flex">
                    <RobotIcon />
                    <Text className="ml-1">{persona.name}</Text>
                  </div>
                </Bubble>
              );
            })}
          </div>
        ) : (
          <>
            <Text>{t("admin.groups.noAgents")}</Text>
          </>
        )}
      </div>

      <Separator />

      <h2 className="text-xl font-bold mt-8 mb-2">
        {t("admin.groups.tokenRateLimitsSection")}
      </h2>

      <AddTokenRateLimitForm
        isOpen={addRateLimitFormVisible}
        setIsOpen={setAddRateLimitFormVisible}
        userGroupId={userGroup.id}
      />

      <GenericTokenRateLimitTable
        fetchUrl={`/api/admin/token-rate-limits/user-group/${userGroup.id}`}
        hideHeading
        isAdmin={isAdmin}
      />

      {isAdmin && (
        <Button
          className="mt-3"
          onClick={() => setAddRateLimitFormVisible(true)}
        >
          {t("admin.groups.createTokenRateLimitButton")}
        </Button>
      )}
    </div>
  );
};
