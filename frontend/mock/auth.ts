import type { MockMethod } from "vite-plugin-mock";

// 模拟后端的账号库
const USERS: Record<
  string,
  { id: number; name: string; avatar: string; password: string }
> = {
  111: { id: 1, name: "admin", avatar: "", password: "111" },
  demo: { id: 2, name: "Demo用户", avatar: "", password: "123456" },
};

export default [
  {
    url: "/api/auth/login",
    method: "post",
    timeout: 300,
    response: ({ body }: { body: { account?: string; password?: string } }) => {
      const account = body?.account?.trim();
      const password = body?.password;
      if (!account || !password) {
        return { code: 1, message: "账号或密码不能为空" };
      }
      const user = USERS[account];
      if (!user || user.password !== password) {
        return { code: 1, message: "账号或密码错误" };
      }
      return {
        code: 0,
        message: "登录成功",
        data: {
          token: "mock-token-" + Math.random().toString(36).slice(2),
          user: { id: user.id, name: user.name, avatar: user.avatar },
        },
      };
    },
  },
  {
    url: "/api/auth/register",
    method: "post",
    timeout: 300,
    response: ({
      body,
    }: {
      body: { account?: string; password?: string };
    }) => {
      const account = body?.account?.trim();
      const password = body?.password;
      if (!account || !password)
        return { code: 1, message: "账号和密码不能为空" };
      if (password.length < 6) return { code: 1, message: "密码至少 6 位" };
      if (USERS[account]) return { code: 1, message: "该账号已被注册" };
      const id = Date.now();
      USERS[account] = { id, name: account, avatar: "", password };
      return {
        code: 0,
        message: "注册成功",
        data: {
          token: "mock-token-" + Math.random().toString(36).slice(2),
          user: { id, name: account, avatar: "" },
        },
      };
    },
  },
] as MockMethod[];
