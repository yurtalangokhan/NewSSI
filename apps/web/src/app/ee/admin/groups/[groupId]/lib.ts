import { accessEndpoints } from "@/lib/api/domains/access/endpoints";

import { updateUserGroupResponse } from "@/lib/api/domains/access/api";
import { updateCuratorStatusResponse } from "@/lib/api/domains/access/api";

import {
  UserGroupUpdate,
  SetCuratorRequest,
} from "@/lib/api/domains/access/group-types";

export const updateUserGroup = async (
  groupId: number,
  userGroup: UserGroupUpdate
) => {
  const url = accessEndpoints.deleteUserGroup(groupId).browserPath;
  return await updateUserGroupResponse(groupId, userGroup);
};

export const updateCuratorStatus = async (
  groupId: number,
  curatorRequest: SetCuratorRequest
) => {
  const url = accessEndpoints.updateCuratorStatus(groupId).browserPath;
  return await updateCuratorStatusResponse(groupId, curatorRequest);
};
