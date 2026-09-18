import request from "@/api/request";

/** 用户级偏好（跟着账号走，存在服务端） */
export interface UserPreferences {
  /** 是否允许添加"官网不可达"的竞品 */
  allowUnreachableOfficial: boolean;
  /** 新增竞品时默认勾选的监控页面类型 */
  defaultSourceTypes: string[];
}

/** 读取当前账号的偏好 */
export function fetchMyPreferences(): Promise<UserPreferences> {
  return request.get<unknown, UserPreferences>("/api/users/me/preferences");
}

/** 局部更新偏好：只传要改的字段，其余保持不变 */
export function saveMyPreferences(
  patch: Partial<UserPreferences>,
): Promise<UserPreferences> {
  return request.put<unknown, UserPreferences>("/api/users/me/preferences", patch);
}
