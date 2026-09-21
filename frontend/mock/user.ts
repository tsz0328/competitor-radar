import { authUser, db, err, ok, userProfile } from "./db";

function requireUser(headers: any) {
  return authUser(headers) || null;
}

/** 账号名与邮箱共享登录命名空间：新值不能撞上别人的账号名或邮箱 */
function taken(d: any, selfId: number, value: string): boolean {
  if (!value) return false;
  const v = value.trim().toLowerCase();
  return d.users.some(
    (u: any) =>
      u.id !== selfId &&
      ((u.username || "").toLowerCase() === v || (u.email || "").toLowerCase() === v),
  );
}

const USERNAME_RE = /^[A-Za-z0-9_-]{3,30}$/;
const PASSWORD_MIN = 6;

export default [
  {
    url: "/api/users/me",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      return ok(userProfile(u));
    },
  },
  {
    url: "/api/users/me",
    method: "put",
    timeout: 200,
    response: ({ headers, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      if (body?.username !== undefined) {
        const username = (body.username ?? "").trim();
        if (!username) return err(40002, "账号名不能为空");
        if (!USERNAME_RE.test(username)) return err(40013, "账号名需 3-30 位，仅字母/数字/下划线/中划线");
        if (taken(d, u.id, username)) return err(40011, "该账号名已被占用");
        u.username = username;
      }
      if (body?.nickname !== undefined) u.name = body.nickname ?? "";
      if (body?.avatar !== undefined) u.avatar = body.avatar ?? "";
      return ok(userProfile(u));
    },
  },
  {
    url: "/api/users/me/preferences",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      return ok(u.preferences || { allowUnreachableOfficial: false, defaultSourceTypes: ["homepage"] });
    },
  },
  {
    url: "/api/users/me/preferences",
    method: "put",
    timeout: 200,
    response: ({ headers, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      if (!u.preferences) u.preferences = { allowUnreachableOfficial: false, defaultSourceTypes: ["homepage"] };
      const patch = body || {};
      if (typeof patch.allowUnreachableOfficial === "boolean") {
        u.preferences.allowUnreachableOfficial = patch.allowUnreachableOfficial;
      }
      if (Array.isArray(patch.defaultSourceTypes)) {
        u.preferences.defaultSourceTypes = patch.defaultSourceTypes;
      }
      return ok(u.preferences);
    },
  },
  {
    url: "/api/users/me/email",
    method: "put",
    timeout: 200,
    response: ({ headers, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const d = db();
      const email = (body?.email ?? "").trim();

      // 解绑：邮箱清空（需已设置密码，否则解绑后无登录手段）
      if (!email) {
        if (!u.password) return err(40015, "尚未设置密码，不能解绑邮箱");
        u.email = "";
        return ok(userProfile(u));
      }

      // 绑定/换绑：必须带正确验证码
      const code = (body?.code ?? "").trim();
      if (!code) return err(40008, "请先获取验证码");
      if (code !== "123456") return err(40008, "验证码错误");
      if (taken(d, u.id, email)) return err(40011, "该邮箱已被占用");
      u.email = email;
      return ok(userProfile(u));
    },
  },
  {
    url: "/api/users/me/password",
    method: "put",
    timeout: 200,
    response: ({ headers, body }: any) => {
      const u = requireUser(headers);
      if (!u) return err(40100, "未登录或登录已过期");
      const oldPassword = body?.oldPassword ?? "";
      const newPassword = body?.newPassword ?? "";
      if ((newPassword || "").length < PASSWORD_MIN) return err(40011, "新密码至少 6 位");
      // 已有密码的账号必须校验原密码（oldPassword 为空只有"验证码登录自动建号"场景允许）
      if (u.password && oldPassword !== u.password) return err(40005, "原密码错误");
      u.password = newPassword;
      return ok(null);
    },
  },
];