import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Table,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import CenteredPageSelector from "./CenteredPageSelector";
import { ThreeDotsLoader } from "@/components/Loading";
import { InvitedUserSnapshot } from "@/lib/types";
import { TableHeader } from "@/components/ui/table";
import { InviteUserButton } from "./buttons/InviteUserButton";
import { ErrorCallout } from "@/components/ErrorCallout";
import { FetchError } from "@/lib/fetcher";

const USERS_PER_PAGE = 10;

interface Props {
  users: InvitedUserSnapshot[];
  mutate: () => void;
  error: FetchError | null;
  isLoading: boolean;
  q: string;
}

const InvitedUserTable = ({ users, mutate, error, isLoading, q }: Props) => {
  const { t } = useTranslation();
  const [currentPageNum, setCurrentPageNum] = useState<number>(1);

  if (!users.length)
    return <p>{t("admin.users.invitedEmptyState")}</p>;

  const totalPages = Math.ceil(users.length / USERS_PER_PAGE);

  // Filter users based on the search query
  const filteredUsers = q
    ? users.filter((user) => user.email.includes(q))
    : users;

  // Get the current page of users
  const currentPageOfUsers = filteredUsers.slice(
    (currentPageNum - 1) * USERS_PER_PAGE,
    currentPageNum * USERS_PER_PAGE
  );

  if (isLoading) {
    return <ThreeDotsLoader />;
  }

  if (error) {
    return (
      <ErrorCallout
        errorTitle={t("admin.users.errorLoadingUsers")}
        errorMsg={error?.info?.detail}
      />
    );
  }

  return (
    <>
      <Table className="overflow-visible">
        <TableHeader>
          <TableRow>
            <TableHead>{t("admin.users.emailHeader")}</TableHead>
            <TableHead>
              <div className="flex justify-end">{t("admin.users.actionsHeader")}</div>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {currentPageOfUsers.length ? (
            currentPageOfUsers.map((user) => (
              <TableRow key={user.email}>
                <TableCell>{user.email}</TableCell>
                <TableCell>
                  <div className="flex justify-end">
                    <InviteUserButton
                      user={user}
                      invited={true}
                      mutate={mutate}
                    />
                  </div>
                </TableCell>
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={2} className="h-24 text-center">
                {t("admin.users.noUsersFoundMatching", { query: q })}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {totalPages > 1 ? (
        <CenteredPageSelector
          currentPage={currentPageNum}
          totalPages={totalPages}
          onPageChange={setCurrentPageNum}
        />
      ) : null}
    </>
  );
};

export default InvitedUserTable;
