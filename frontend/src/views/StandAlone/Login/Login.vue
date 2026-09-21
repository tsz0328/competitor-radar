<script setup lang="ts">
import { reactive, ref, onBeforeUnmount } from "vue";
import { useAuth } from "@/composables/useAuth";
import { useRouter } from "vue-router";
import {
  User,
  Lock,
  Message,
  Key,
  ArrowLeft,
  ArrowRight,
} from "@element-plus/icons-vue";
import Logo from "@/components/Logo.vue";
import BrandPanel from "@/views/StandAlone/Login/BrandPanel.vue";
import { readRememberPreference } from "@/utils/authStorage";
import { sendEmailCode } from "@/api/auth";
import {
  ACCOUNT_RULE_HINT,
  isValidAccount,
  isValidEmail,
  normalizeAccount,
  normalizeEmail,
} from "@/utils/validators";
import { ElMessage } from "element-plus";
import type { EmailCodeScene } from "@/types/auth";

const router = useRouter();

/** 当前 Tab（登录 / 注册）；「忘记密码」是独立视图，会盖掉 Tab 区 */
const activeTab = ref<"login" | "register">("login");
/** 登录方式：密码登录 / 邮箱验证码登录 */
const loginMode = ref<"password" | "code">("password");
/** 忘记密码视图：占用同一个表单位置，配一条「返回登录」 */
const resetVisible = ref(false);

// 表单数据
// 「记住我」：勾选 → 登录态存 localStorage（关掉浏览器仍登录，后端签长期令牌）；
//            不勾 → 只存 sessionStorage（关掉浏览器需重新登录，后端签会话令牌）
// 默认值取上次登录时的选择，常见用户预期是「上次勾了这次还勾着」
const loginForm = reactive({
  // account 是「账号或邮箱」：两种标识都能登录，后端按 OR 查
  account: "",
  password: "",
  remember: readRememberPreference(),
});

// 验证码登录 / 注册 / 重置密码三个表单
const codeLoginForm = reactive({
  // 验证码登录只认邮箱（这个信箱就是收码的地方）
  email: "",
  code: "",
  remember: readRememberPreference(),
});
const registerForm = reactive({
  // 账号必填；邮箱选填，填了才出现验证码那一行
  username: "",
  email: "",
  code: "",
  password: "",
  confirm: "",
});
const resetForm = reactive({
  // 账号或邮箱都行；验证码是发到「该账号绑定的邮箱」上的
  account: "",
  code: "",
  password: "",
  confirm: "",
});

const {
  login: doLogin,
  register: doRegister,
  loginByCode: doLoginByCode,
  resetPassword: doResetPassword,
  loading: authLoading,
} = useAuth();

/**
 * 验证码发送器：倒计时 + 发送中状态 + 邮箱格式预校验。
 * 登录/注册共用同一场景（login），重置密码单独一个场景——两边的码不通用。
 */
function useCodeSender(scene: EmailCodeScene, fallbackHint: string) {
  const sending = ref(false);
  const seconds = ref(0);
  let timer: number | undefined;

  function stop() {
    if (timer !== undefined) {
      window.clearInterval(timer);
      timer = undefined;
    }
  }

  async function send(value: string) {
    if (seconds.value > 0 || sending.value) return;
    const raw = value.trim();
    if (!raw) {
      ElMessage.warning(scene === "reset" ? "请先填写账号或邮箱" : "请先填写邮箱");
      return;
    }
    // 登录 / 绑定邮箱场景必须是邮箱——验证码就是发到这个信箱来证明归属的；
    // 重置密码场景可以是账号或邮箱，后端自己会定位账号再往它绑定的邮箱发码。
    if (scene !== "reset" && !isValidEmail(raw)) {
      ElMessage.warning("邮箱格式不正确");
      return;
    }
    sending.value = true;
    try {
      await sendEmailCode(scene === "reset" ? raw : normalizeEmail(raw), scene);
      ElMessage.success("验证码已发送，请查收邮箱（含垃圾箱）");
      seconds.value = 60;
      stop();
      timer = window.setInterval(() => {
        seconds.value -= 1;
        if (seconds.value <= 0) stop();
      }, 1000);
    } catch (e) {
      // 具体原因（重发过快 / SMTP 未配置）由 request.ts 统一弹出，这里只兜住倒计时
      ElMessage.error((e as Error).message || fallbackHint);
    } finally {
      sending.value = false;
    }
  }

  onBeforeUnmount(stop);
  return { sending, seconds, send };
}

const {
  sending: loginCodeSending,
  seconds: loginCodeSeconds,
  send: sendLoginCode,
} = useCodeSender("login", "验证码发送失败");
const {
  sending: registerCodeSending,
  seconds: registerCodeSeconds,
  send: sendRegisterCode,
} = useCodeSender("login", "验证码发送失败");
const {
  sending: resetCodeSending,
  seconds: resetCodeSeconds,
  send: sendResetCode,
} = useCodeSender("reset", "验证码发送失败");

/** 邮箱格式不通过就不发请求：省一次注定失败的往返 */
function requireEmail(email: string): string | null {
  if (!email.trim()) {
    ElMessage.warning("请填写邮箱");
    return null;
  }
  if (!isValidEmail(email)) {
    ElMessage.warning("邮箱格式不正确");
    return null;
  }
  return normalizeEmail(email);
}

/**
 * 账号或邮箱：只做非空校验。
 *
 * 刻意**不校验格式**——两种标识形态完全不同，用一个规则去卡只会误伤
 * （拿邮箱当账号名填、或者账号名里带下划线）。填错了后端自然查不到，
 * 回一句「账号或密码错误」就够了。
 */
function requireIdentifier(value: string): string | null {
  const raw = value.trim();
  if (!raw) {
    ElMessage.warning("请填写账号或邮箱");
    return null;
  }
  return raw;
}

// 登录提交（密码）：account 传账号或邮箱，两种都认
const onLogin = () => {
  const account = requireIdentifier(loginForm.account);
  if (!account) return;
  if (!loginForm.password) {
    ElMessage.warning("请填写密码");
    return;
  }
  doLogin({
    account,
    password: loginForm.password,
    remember: loginForm.remember,
  });
};

// 登录提交（邮箱验证码）：邮箱没注册过时后端会自动建号
const onCodeLogin = () => {
  const email = requireEmail(codeLoginForm.email);
  if (!email) return;
  if (!codeLoginForm.code.trim()) {
    ElMessage.warning("请填写验证码");
    return;
  }
  doLoginByCode({
    email,
    code: codeLoginForm.code.trim(),
    remember: codeLoginForm.remember,
  });
};

// 注册提交：账号必填 + 邮箱选填（填了就必须带验证码）+ 密码
const onRegister = async () => {
  const username = normalizeAccount(registerForm.username);
  if (!username) {
    ElMessage.warning("请设置登录账号");
    return;
  }
  if (!isValidAccount(username)) {
    ElMessage.warning(ACCOUNT_RULE_HINT);
    return;
  }
  const rawEmail = registerForm.email.trim();
  if (rawEmail && !isValidEmail(rawEmail)) {
    ElMessage.warning("邮箱格式不正确");
    return;
  }
  const email = rawEmail ? normalizeEmail(rawEmail) : "";
  if (email && !registerForm.code.trim()) {
    ElMessage.warning("请填写邮箱验证码");
    return;
  }
  const { password, confirm } = registerForm;
  if (!password) {
    ElMessage.warning("请填写密码");
    return;
  }
  if (password.length < 6) {
    ElMessage.warning("密码至少 6 位");
    return;
  }
  if (password !== confirm) {
    ElMessage.warning("两次输入的密码不一致");
    return;
  }
  await doRegister({
    username,
    email,
    // 没填邮箱就压根不传 code：后端也只在给了邮箱时才验码
    code: email ? registerForm.code.trim() : undefined,
    password,
  });
};

// 忘记密码 → 用邮箱验证码重置（account 可以是账号或邮箱）
function openReset() {
  resetForm.account = loginForm.account;
  resetVisible.value = true;
}

function closeReset() {
  resetVisible.value = false;
  resetForm.code = "";
  resetForm.password = "";
  resetForm.confirm = "";
}

const onReset = async () => {
  const account = requireIdentifier(resetForm.account);
  if (!account) return;
  if (!resetForm.code.trim()) {
    ElMessage.warning("请填写验证码");
    return;
  }
  if (resetForm.password.length < 6) {
    ElMessage.warning("新密码至少 6 位");
    return;
  }
  if (resetForm.password !== resetForm.confirm) {
    ElMessage.warning("两次输入的新密码不一致");
    return;
  }
  await doResetPassword({
    account,
    code: resetForm.code.trim(),
    newPassword: resetForm.password,
  });
};
</script>

<template>
  <div class="login-page">
    <!-- 左侧品牌面板 -->
    <section class="brand-panel">
      <BrandPanel />
    </section>

    <!-- 右侧表单面板 -->
    <section class="form-panel">
      <div class="form-top">
        <el-button
          class="form-link back-btn"
          link
          @click="router.push({ name: 'Landing' })"
        >
          <el-icon>
            <ArrowLeft />
          </el-icon>
          返回首页
        </el-button>
      </div>

      <div class="form-brand">
        <Logo size="1.5em" />
        <span class="form-brand-name">竞品雷达</span>
      </div>

      <div class="form-title">
        {{ resetVisible ? "重置密码" : "欢迎使用" }}
      </div>
      <div class="form-subtitle">
        {{
          resetVisible
            ? "输入邮箱验证码，为你的账号设置新密码"
            : "登录以继续你的市场情报分析之旅"
        }}
      </div>

      <!-- 登录 / 注册 Tab（重置密码时隐藏，避免竞争视觉焦点） -->
      <div
        v-show="!resetVisible"
        class="form-tabs"
        :style="{ '--tab-index': activeTab === 'login' ? 0 : 1 }"
      >
        <button
          class="form-tab"
          :class="{ active: activeTab === 'login' }"
          @click="activeTab = 'login'"
        >
          登录
        </button>
        <button
          class="form-tab"
          :class="{ active: activeTab === 'register' }"
          @click="activeTab = 'register'"
        >
          注册
        </button>
      </div>

      <!-- 登录 · 密码方式 -->
      <div
        v-show="!resetVisible && activeTab === 'login' && loginMode === 'password'"
        class="form-body"
      >
        <el-input
          v-model="loginForm.account"
          :prefix-icon="User"
          placeholder="请输入账号或邮箱"
          size="large"
        />
        <el-input
          v-model="loginForm.password"
          :prefix-icon="Lock"
          type="password"
          show-password
          placeholder="请输入密码"
          size="large"
          @keyup.enter="onLogin"
        />
        <div class="form-row">
          <el-checkbox
            v-model="loginForm.remember"
            title="勾选后关闭浏览器再打开仍是登录状态；不勾选则关闭浏览器后需要重新登录"
            >记住我</el-checkbox
          >
          <div class="form-row-links">
            <el-button class="form-link forgot-btn" link @click="openReset"
              >忘记密码？</el-button
            >
            <el-button
              class="form-link mode-btn"
              link
              @click="loginMode = 'code'"
              >验证码登录</el-button
            >
          </div>
        </div>
        <el-button
          class="submit-btn"
          type="primary"
          :loading="authLoading"
          @click="onLogin"
        >
          登录
          <el-icon>
            <ArrowRight />
          </el-icon>
        </el-button>
      </div>

      <!-- 登录 · 邮箱验证码方式（邮箱没有账号时会自动注册） -->
      <div
        v-show="!resetVisible && activeTab === 'login' && loginMode === 'code'"
        class="form-body"
      >
        <el-input
          v-model="codeLoginForm.email"
          :prefix-icon="User"
          placeholder="请输入登录邮箱"
          size="large"
        />
        <div class="code-row">
          <el-input
            v-model="codeLoginForm.code"
            :prefix-icon="Message"
            placeholder="6 位验证码"
            size="large"
            maxlength="6"
            @keyup.enter="onCodeLogin"
          />
          <el-button
            class="code-btn"
            :loading="loginCodeSending"
            :disabled="loginCodeSeconds > 0"
            @click="sendLoginCode(codeLoginForm.email)"
          >
            {{ loginCodeSeconds > 0 ? `${loginCodeSeconds}s` : "获取验证码" }}
          </el-button>
        </div>
        <div class="form-row">
          <el-checkbox v-model="codeLoginForm.remember" title="勾选后关闭浏览器再打开仍是登录状态"
            >记住我</el-checkbox
          >
          <el-button
            class="form-link mode-btn"
            link
            @click="loginMode = 'password'"
            >密码登录</el-button
          >
        </div>
        <el-button
          class="submit-btn"
          type="primary"
          :loading="authLoading"
          @click="onCodeLogin"
        >
          登录
          <el-icon>
            <ArrowRight />
          </el-icon>
        </el-button>
        <div class="field-hint">
          该邮箱还没有账号？验证通过后会自动为你创建（账号名默认就是该邮箱，登录后可在用户中心改）。
        </div>
      </div>

      <!-- 注册表单：账号必填；邮箱选填，填了才需要验证码（不验码就可被他人抢注） -->
      <div
        v-show="!resetVisible && activeTab === 'register'"
        class="form-body"
      >
        <el-input
          v-model="registerForm.username"
          :prefix-icon="User"
          placeholder="设置登录账号（3–30 位，字母/数字/下划线/中划线）"
          size="large"
        />
        <el-input
          v-model="registerForm.email"
          :prefix-icon="Message"
          placeholder="邮箱（选填）"
          size="large"
          clearable
        />
        <!-- 验证码按需出现：填了邮箱才展示，避免给「不想填邮箱」的人多一道必填 -->
        <div v-if="registerForm.email.trim()" class="code-row">
          <el-input
            v-model="registerForm.code"
            :prefix-icon="Key"
            placeholder="6 位邮箱验证码"
            size="large"
            maxlength="6"
          />
          <el-button
            class="code-btn"
            :loading="registerCodeSending"
            :disabled="registerCodeSeconds > 0"
            @click="sendRegisterCode(registerForm.email)"
          >
            {{ registerCodeSeconds > 0 ? `${registerCodeSeconds}s` : "获取验证码" }}
          </el-button>
        </div>
        <el-input
          v-model="registerForm.password"
          :prefix-icon="Lock"
          type="password"
          show-password
          placeholder="请设置密码（至少 6 位）"
          size="large"
        />
        <el-input
          v-model="registerForm.confirm"
          :prefix-icon="Lock"
          type="password"
          show-password
          placeholder="请再次输入密码"
          size="large"
          @keyup.enter="onRegister"
        />
        <el-button
          class="submit-btn"
          type="primary"
          :loading="authLoading"
          @click="onRegister"
        >
          注册
        </el-button>
        <div class="field-hint">
          填邮箱可用它登录、接收情报邮件通知，并支持自助找回密码；不填也能用账号密码登录。
        </div>
      </div>

      <!-- 忘记密码：账号或邮箱 → 验证码发到该账号绑定的邮箱 → 设置新密码 -->
      <div v-show="resetVisible" class="form-body">
        <el-input
          v-model="resetForm.account"
          :prefix-icon="User"
          placeholder="请输入账号或邮箱"
          size="large"
        />
        <div class="code-row">
          <el-input
            v-model="resetForm.code"
            :prefix-icon="Key"
            placeholder="6 位验证码"
            size="large"
            maxlength="6"
          />
          <el-button
            class="code-btn"
            :loading="resetCodeSending"
            :disabled="resetCodeSeconds > 0"
            @click="sendResetCode(resetForm.account)"
          >
            {{ resetCodeSeconds > 0 ? `${resetCodeSeconds}s` : "获取验证码" }}
          </el-button>
        </div>
        <el-input
          v-model="resetForm.password"
          :prefix-icon="Lock"
          type="password"
          show-password
          placeholder="请输入新密码（至少 6 位）"
          size="large"
        />
        <el-input
          v-model="resetForm.confirm"
          :prefix-icon="Lock"
          type="password"
          show-password
          placeholder="请再次输入新密码"
          size="large"
          @keyup.enter="onReset"
        />
        <el-button
          class="submit-btn"
          type="primary"
          :loading="authLoading"
          @click="onReset"
        >
          重置并登录
        </el-button>
        <div class="form-row form-row--center">
          <el-button class="form-link mode-btn" link @click="closeReset"
            >返回登录</el-button
          >
        </div>
      </div>

      <div v-show="!resetVisible" class="form-footer">
        还没有账号？
        <el-button
          class="form-link register-btn"
          link
          @click="activeTab = 'register'"
          >立即注册</el-button
        >
      </div>
    </section>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  gap: 5vw;
  padding: 5vh 5vw;
  background: linear-gradient(
    135deg,
    var(--app-color-blue),
    var(--app-color-white-blue)
  );
  height: 100vh;
}

.brand-panel {
  flex: 1;
}

/* 右侧表单面板 */
.form-panel {
  width: 30vw;
  border: 1px solid color-mix(in oklch, var(--app-color-blue) 50%, transparent);
  border-radius: 2vmax;
  box-shadow: 0 6px 24px
    color-mix(in oklch, var(--app-color-blue) 60%, transparent);
  display: flex;
  flex-direction: column;
  padding: 3vh 3vw;
}

.form-top {
  display: flex;
  justify-content: flex-end;
}

.form-link {
  align-items: center;
  padding: 1vh 1vw;
  color: var(--app-color-blue);
}

.form-link:hover {
  color: var(--app-color-blue-light-1);
}

.form-link:active {
  color: var(--app-color-blue-dark-1);
}

.back-btn {
  font-size: 1.2vmax;
}

.form-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6vw;
  margin-top: 2vh;
  font-size: 1.5vmax;
}

.form-brand-name {
  font-weight: bold;
  background: linear-gradient(
    90deg,
    var(--app-color-purple),
    var(--app-color-blue-dark-3)
  );
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.form-title {
  margin: 1.5vh 0 0;
  text-align: center;
  font-size: 1.3vmax;
  font-weight: bold;
  background: linear-gradient(
    90deg,
    var(--app-color-purple),
    var(--app-color-blue-dark-3)
  );
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.form-subtitle {
  margin: 0.8vh 0 0;
  text-align: center;
  font-size: 1vmax;
  color: var(--app-color-gray);
}

/* Tab 切换 */
.form-tabs {
  display: flex;

  margin-top: 2vh;
  border-bottom: 1px solid
    color-mix(in oklch, var(--app-color-gray) 20%, transparent);
  position: relative;
}

/* 指示器：挂在容器上，只有一条 */
.form-tabs::after {
  content: "";
  position: absolute;
  bottom: -1px;
  left: 0;
  width: 50%;
  height: 2px;
  border-radius: 2px;
  background: var(--app-color-blue);
  transform: translateX(calc(var(--tab-index) * 100%));
  transition: transform 0.3s ease;
}

.form-tab {
  flex: 1;
  background: none;
  border: none;
  cursor: pointer;
  padding: 1vh 0.5vw;
  font-size: 1.2vmax;
  color: var(--app-text-color-secondary);
  position: relative;
}

.form-tab.active {
  color: var(--app-color-blue);
  font-weight: bold;
}

/* 表单区 */
.form-body {
  display: flex;
  flex-direction: column;
  gap: 2vh;
  padding: 2.5vh 0;
}

.form-body :deep(.el-input__wrapper) {
  background-color: transparent;
  border: 1px solid color-mix(in oklch, var(--app-color-blue) 80%, transparent);
}

.form-body :deep(.el-input__wrapper:hover) {
  border-color: var(--app-color-blue);
}

.form-body :deep(.el-input__inner) {
  color: var(--app-color-black);
}

/* 浏览器自动填充会强制刷上浅色底 + 固定文字色，导致透明输入框出现白块。
   用超长 transition 延迟阻止 Chrome 覆盖 background-color，并统一文字/光标颜色。 */
.form-body :deep(.el-input__inner:-webkit-autofill),
.form-body :deep(.el-input__inner:-webkit-autofill:hover),
.form-body :deep(.el-input__inner:-webkit-autofill:focus),
.form-body :deep(.el-input__inner:-webkit-autofill:active),
.form-body :deep(.el-input__inner:autofill) {
  background-color: transparent;
  -webkit-text-fill-color: var(--app-color-black);
  caret-color: var(--app-color-black);
  transition: background-color 9999999s ease-in-out 0s;
}

.form-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.form-row--center {
  justify-content: center;
}

.form-row-links {
  display: flex;
  align-items: center;
  gap: 0.4vw;
}

/* 验证码一行：输入框占满剩余宽度，按钮靠右并自动拉伸到与输入框等高 */
.code-row {
  display: flex;
  gap: 0.8vw;
}

.code-row :deep(.el-input) {
  flex: 1;
  min-width: 0;
}

.code-btn {
  flex: none;
  --el-border-radius-base: 0.8vmax;
  --el-font-size-base: 1.2vmax;
  margin: 0;
  padding: 0 1vw;
}

.forgot-btn,
.mode-btn,
.register-btn {
  font-size: 1vmax;
}

.form-body :deep(.el-checkbox__inner) {
  background-color: transparent;
  border: 1px solid color-mix(in oklch, var(--app-color-blue) 50%, transparent);
}

.form-body :deep(.el-checkbox.is-checked .el-checkbox__inner) {
  border-color: var(--app-color-blue);
}

/* 字段说明：小字、浅色，解释「为什么还要填这一步」 */
.field-hint {
  font-size: 0.9vmax;
  line-height: 1.6;
  color: var(--app-color-gray);
}

/* 登录/注册按钮：样式由全局移入本页（原先依赖 global.css 的 .el-button 字号） */
.submit-btn {
  --el-border-radius-base: 0.8vmax;
  font-size: 1.5vmax;
  height: auto;
  width: 100%;
  margin: 0;
  border: none;
  background: linear-gradient(
    135deg,
    var(--app-color-blue-light-2),
    var(--app-color-purple)
  );
  box-shadow: 0 4px 16px
    color-mix(in oklch, var(--app-color-blue) 20%, transparent);
  transition: all 0.2s ease;
}

.submit-btn:hover {
  background: linear-gradient(
    135deg,
    var(--app-color-blue-light-3),
    var(--app-color-purple-light-1)
  );
  box-shadow: 0 6px 24px
    color-mix(in oklch, var(--app-color-purple) 30%, transparent);
}

.submit-btn:active {
  box-shadow: 0 2px 8px
    color-mix(in oklch, var(--app-color-purple) 30%, transparent);
  transform: translateY(1px);
}

.form-footer {
  margin: 2vh 0 0;
  text-align: center;
  font-size: 1.2vmax;
  color: var(--app-text-color-secondary);
}
</style>
