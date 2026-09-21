import {
  adminUser,
  authUser,
  cleanHost,
  db,
  err,
  idFrom,
  ok,
  serializeCompetitor,
} from "./db";

function requireAdmin(headers: any) {
  const u = authUser(headers);
  if (!u) return null;
  if (!u.isAdmin) return "forbidden";
  return u;
}

function guard(headers: any) {
  const a = requireAdmin(headers);
  if (a === null) return err(40100, "未登录或登录已过期");
  if (a === "forbidden") return err(40300, "无权限，仅管理员可操作");
  return null;
}

const USERNAME_RE = /^[A-Za-z0-9_-]{3,30}$/;

export default [
  {
    url: "/api/admin/system-settings",
    method: "get",
    timeout: 200,
    response: ({ headers }: any) => {
      const g = guard(headers);
      if (g) return g;
      return ok(db().systemSettings);
    },
  },
  {
    url: "/api/admin/system-settings",
    method: "put",
    timeout: 200,
    response: ({ headers, body }: any) => {
      const g = guard(headers);
      if (g) return g;
      const s = db().systemSettings;
      const p = body || {};
      if (p.smtp_host !== undefined) s.smtp_host = p.smtp_host || "";
      if (p.smtp_port !== undefined) s.smtp_port = p.smtp_port || 25;
      if (p.smtp_username !== undefined) s.smtp_username = p.smtp_username || "";
      if (p.smtp_sender !== undefined) s.smtp_sender = p.smtp_sender || "";
      // 授权码：空串 = 不改动；非空 = 更新（明文不回传，仅标记 set）
      if (p.smtp_password !== undefined && p.smtp_password !== "") {
        s.smtp_password_set = true;
        s._password = p.smtp_password;
      }
      return ok(s);
    },
  },
  {
    url: "/api/admin/users",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const keyword = ((query?.keyword || "") as string).trim().toLowerCase();
      const list = d.users
        .filter((u: any) => {
          if (!keyword) return true;
          return (u.username || "").toLowerCase().includes(keyword) || (u.email || "").toLowerCase().includes(keyword);
        })
        .map(adminUser);
      return ok(list);
    },
  },
  {
    url: "/api/admin/users/:id",
    method: "put",
    timeout: 200,
    response: ({ headers, url, body }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const id = Number(url.split("?")[0].split("/").filter((s: string) => /^\d+$/.test(s)).pop());
      const u = d.users.find((x: any) => x.id === id);
      if (!u) return err(40402, "用户不存在");
      const patch = body || {};
      if (patch.username !== undefined) {
        const username = (patch.username ?? "").trim();
        if (!username) return err(40002, "账号名不能为空");
        if (!USERNAME_RE.test(username)) return err(40013, "账号名需 3-30 位，仅字母/数字/下划线/中划线");
        const v = username.toLowerCase();
        const clash = d.users.some(
          (x: any) => x.id !== id && ((x.username || "").toLowerCase() === v || (x.email || "").toLowerCase() === v),
        );
        if (clash) return err(40011, "该账号名已被占用");
        u.username = username;
      }
      if (patch.is_admin !== undefined) u.isAdmin = !!patch.is_admin;
      if (patch.is_active !== undefined) u.active = !!patch.is_active;
      if (patch.new_password !== undefined && patch.new_password !== "") {
        if ((patch.new_password || "").length < 6) return err(40011, "新密码至少 6 位");
        u.password = patch.new_password;
      }
      return ok(adminUser(u));
    },
  },
  {
    url: "/api/admin/users/:id",
    method: "delete",
    timeout: 200,
    response: ({ headers, url }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const id = Number(url.split("?")[0].split("/").filter((s: string) => /^\d+$/.test(s)).pop());
      const idx = d.users.findIndex((x: any) => x.id === id);
      if (idx < 0) return err(40402, "用户不存在");
      d.users.splice(idx, 1);
      return ok(null);
    },
  },
  {
    url: "/api/admin/competitors",
    method: "get",
    timeout: 200,
    response: ({ headers, query }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const keyword = ((query?.keyword || "") as string).trim().toLowerCase();
      const userById: Record<number, any> = Object.fromEntries(
        d.users.map((u: any) => [u.id, u]),
      );
      const list = d.competitors
        .filter((c: any) => !c.deletedAt)
        .filter(
          (c: any) =>
            !keyword ||
            (c.name || "").toLowerCase().includes(keyword) ||
            (c.officialUrl || "").toLowerCase().includes(keyword),
        )
        .map((c: any) => {
          const owner = userById[c.userId];
          return {
            ...serializeCompetitor(c),
            ownerUsername: owner?.username ?? "",
            ownerNickname: owner?.name ?? "",
          };
        });
      return ok(list);
    },
  },
  {
    // 注意：content-type 为 multipart/form-data，vite-plugin-mock 不解析文件内容，
    // 这里只回填一个托管地址并同步同域名竞品的 logoUrl，模拟后端行为
    url: "/api/admin/competitors/:id/icon",
    method: "post",
    timeout: 300,
    response: ({ headers, url }: any) => {
      const g = guard(headers);
      if (g) return g;
      const d = db();
      const id = idFrom(url);
      const c = d.competitors.find((x: any) => x.id === id && !x.deletedAt);
      if (!c) return err(40401, "竞品不存在");
      const logoUrl = `/api/icons/mock-${id}.png`;
      const host = cleanHost(c.officialUrl);
      d.competitors.forEach((x: any) => {
        if (!x.deletedAt && cleanHost(x.officialUrl) === host) x.logoUrl = logoUrl;
      });
      return ok({ logoUrl });
    },
  },
];