import {
  authUser,
  db,
  err,
  ok,
  mintToken,
  userBrief,
} from "./db";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// 无真实邮箱服务，验证码固定为 123456 方便联调；也记录最近一次下发码
const TEST_CODE = "123456";

function findByIdentifier(account: string): any | null {
  const d = db();
  const key = (account || "").trim().toLowerCase();
  if (!key) return null;
  return (
    d.users.find((u) => u.username.toLowerCase() === key) ||
    d.users.find((u) => (u.email || "").toLowerCase() === key) ||
    null
  );
}

export default [
  {
    url: "/api/auth/login",
    method: "post",
    timeout: 300,
    response: ({ body }: any) => {
      const account = (body?.account ?? "").trim();
      const password = body?.password ?? "";
      if (!account || !password) return err(40101, "请输入账号和密码");
      const user = findByIdentifier(account);
      if (!user || user.password !== password) return err(40101, "账号或密码错误");
      if (!user.active) return err(40104, "账号已被停用");
      return ok({ token: mintToken(user.id), user: userBrief(user) });
    },
  },
  {
    url: "/api/auth/register",
    method: "post",
    timeout: 300,
    response: ({ body }: any) => {
      const d = db();
      const username = (body?.username ?? "").trim();
      const password = body?.password ?? "";
      const email = (body?.email ?? "").trim();
      const code = body?.code ?? "";

      if (!username) return err(40013, "账号名不能为空");
      if (!/^[a-zA-Z0-9_-]{3,30}$/.test(username)) return err(40013, "账号名需 3–30 位字母/数字/下划线/中划线");
      if (password.length < 6) return err(40011, "密码至少 6 位");
      if (findByIdentifier(username)) return err(40001, "该账号已被注册");

      if (email) {
        if (!EMAIL_RE.test(email)) return err(40006, "邮箱格式不正确");
        if (findByIdentifier(email)) return err(40011, "该邮箱已被其它账号占用");
        if (code !== TEST_CODE) return err(40008, "验证码错误或已过期");
      }

      const id = d.seq.user++;
      const user = {
        id,
        username,
        name: username,
        password,
        email: email || "",
        avatar: "",
        isAdmin: false,
        active: true,
        preferences: { allowUnreachableOfficial: false, defaultSourceTypes: ["homepage"] },
      };
      d.users.push(user);
      return ok({ token: mintToken(id), user: userBrief(user) });
    },
  },
  {
    url: "/api/auth/email-code",
    method: "post",
    timeout: 300,
    response: ({ body }: any) => {
      const d = db();
      const account = (body?.account ?? "").trim();
      const scene = body?.scene ?? "login";
      if (!account) return err(40006, "请输入邮箱");
      if (scene === "login" && !EMAIL_RE.test(account)) return err(40006, "邮箱格式不正确");
      if (scene === "reset") {
        const user = findByIdentifier(account);
        if (!user) return err(40402, "用户不存在");
        if (!user.email) return err(40015, "该账号还没有绑定邮箱");
      }
      // 记录并返回验证码（无真实发信通道，返回码便于联调）
      d.emailCodes[`${scene}:${account.toLowerCase()}`] = TEST_CODE;
      return ok({ code: TEST_CODE, message: `验证码已下发（${account}）：${TEST_CODE}` });
    },
  },
  {
    url: "/api/auth/login-by-code",
    method: "post",
    timeout: 300,
    response: ({ body }: any) => {
      const d = db();
      const email = (body?.email ?? "").trim();
      const code = body?.code ?? "";
      if (!EMAIL_RE.test(email)) return err(40006, "邮箱格式不正确");
      if (code !== TEST_CODE) return err(40008, "验证码错误或已过期");

      let user = findByIdentifier(email);
      if (!user) {
        user = {
          id: d.seq.user++,
          username: email,
          name: email.split("@")[0],
          password: "",
          email,
          avatar: "",
          isAdmin: false,
          active: true,
          preferences: { allowUnreachableOfficial: false, defaultSourceTypes: ["homepage"] },
        };
        d.users.push(user);
      }
      return ok({ token: mintToken(user.id), user: userBrief(user) });
    },
  },
  {
    url: "/api/auth/reset-password",
    method: "post",
    timeout: 300,
    response: ({ body }: any) => {
      const account = (body?.account ?? "").trim();
      const code = body?.code ?? "";
      const newPassword = body?.newPassword ?? "";
      const user = findByIdentifier(account);
      if (!user) return err(40402, "用户不存在");
      if (!user.email) return err(40015, "该账号还没有绑定邮箱");
      if (code !== TEST_CODE) return err(40008, "验证码错误或已过期");
      if (newPassword.length < 6) return err(40011, "新密码至少 6 位");
      user.password = newPassword;
      return ok({ token: mintToken(user.id), user: userBrief(user) });
    },
  },
  {
    url: "/api/auth/refresh",
    method: "post",
    timeout: 300,
    response: ({ headers }: any) => {
      const user = authUser(headers);
      if (!user) return err(40102, "令牌无效或已过期");
      return ok({ token: mintToken(user.id), user: userBrief(user) });
    },
  },
];