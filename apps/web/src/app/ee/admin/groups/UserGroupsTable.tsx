"use client";

import {
  Table,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import { toast } from "@/hooks/useToast";
import { LoadingAnimation } from "@/components/Loading";
import { ConnectorTitle } from "@/components/admin/connectors/ConnectorTitle";
import { deleteUserGroup } from "./lib";
import { useRouter } from "next/navigation";
import { FiUser } from "react-icons/fi";
import { User, UserGroup } from "@/lib/types";
import { DeleteButton } from "@/components/DeleteButton";
import { TableHeader } from "@/components/ui/table";
import Button from "@/refresh-components/buttons/Button";
import { SvgEdit } from "@opal/icons";
import { useTranslation } from "react-i18next";
const MAX_USERS_TO_DISPLAY = 6;

const SimpleUserDisplay = ({ user }: { user: User }) => {
  const { t } = useTranslation();
  return (
    <div className="flex my-0.5">
      <FiUser className="mr-2 my-auto" /> {user.email}
    </div>
  );
};

interface UserGroupsTableProps {
  userGroups: UserGroup[];
  refresh: () => void;
}

export const UserGroupsTable = ({
  userGroups,
  refresh,
}: UserGroupsTableProps) => {
  const { t } = useTranslation();
  const router = useRouter();

  // sort by name for consistent ordering
  userGroups.sort((a, b) => {
    if (a.name < b.name) {
      return -1;
    } else if (a.name > b.name) {
      return 1;
    } else {
      return 0;
    }
  });

  return (
    <div>
      <Table className="overflow-visible">
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>{t("admin.groups.connectorsHeader")}</TableHead>
            <TableHead>{t("admin.groups.usersHeader")}</TableHead>
            <TableHead>{t("admin.groups.statusHeader")}</TableHead>
            <TableHead>{t("admin.groups.deleteHeader")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {userGroups
            .filter((userGroup) => !userGroup.is_up_for_deletion)
            .map((userGroup) => {
              return (
                <TableRow key={userGroup.id}>
                  <TableCell>
                    <Button
                      internal
                      leftIcon={SvgEdit}
                      href={`/admin/groups/${userGroup.id}`}
                      className="truncate"
                    >
                      {userGroup.name}
                    </Button>
                  </TableCell>
                  <TableCell>
                    {userGroup.cc_pairs.length > 0 ? (
                      <div>
                        {userGroup.cc_pairs.map((ccPairDescriptor, ind) => {
                          return (
                            <div
                              className={
                                ind !== userGroup.cc_pairs.length - 1
                                  ? "mb-3"
                                  : ""
                              }
                              key={ccPairDescriptor.id}
                            >
                              <ConnectorTitle
                                connector={ccPairDescriptor.connector}
                                ccPairId={ccPairDescriptor.id}
                                ccPairName={ccPairDescriptor.name}
                                showMetadata={false}
                              />
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      "-"
                    )}
                  </TableCell>
                  <TableCell>
                    {userGroup.users.length > 0 ? (
                      <div>
                        {userGroup.users.length <= MAX_USERS_TO_DISPLAY ? (
                          userGroup.users.map((user) => {
                            return (
                              <SimpleUserDisplay key={user.id} user={user} />
                            );
                          })
                        ) : (
                          <div>
                            {userGroup.users
                              .slice(0, MAX_USERS_TO_DISPLAY)
                              .map((user) => {
                                return (
                                  <SimpleUserDisplay
                                    key={user.id}
                                    user={user}
                                  />
                                );
                              })}
                            <div>
                              + {userGroup.users.length - MAX_USERS_TO_DISPLAY}{" "}
                              {t("admin.groups.moreUsers")}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      "-"
                    )}
                  </TableCell>
                  <TableCell>
                    {userGroup.is_up_to_date ? (
                      <div className="text-success">
                        {t("admin.groups.upToDate")}
                      </div>
                    ) : (
                      <div className="w-10">
                        <LoadingAnimation text={t("admin.groups.syncing")} />
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <DeleteButton
                      onClick={async (event) => {
                        event.stopPropagation();
                        const response = await deleteUserGroup(userGroup.id);
                        if (response.ok) {
                          toast.success(
                            t("admin.groups.deleted", { name: userGroup.name })
                          );
                        } else {
                          const errorMsg = (await response.json()).detail;
                          toast.error(
                            t("admin.groups.deleteFailed", { errorMsg })
                          );
                        }
                        refresh();
                      }}
                    />
                  </TableCell>
                </TableRow>
              );
            })}
        </TableBody>
      </Table>
    </div>
  );
};
