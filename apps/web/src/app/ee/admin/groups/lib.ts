import { authenticatedFetch } from "@/lib/fetcher";
import { UserGroupCreation } from "./types";

export const createUserGroup = async (userGroup: UserGroupCreation) => {
  return authenticatedFetch("/api/manage/admin/user-group", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(userGroup),
  });
};

export const deleteUserGroup = async (userGroupId: number) => {
  return authenticatedFetch(`/api/manage/admin/user-group/${userGroupId}`, {
    method: "DELETE",
  });
};
