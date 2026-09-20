<script setup lang="ts">
import { ref, reactive } from "vue";
import { useAuth } from "@/composables/useAuth";
import { useRouter } from "vue-router";
import {
  User,
  Lock,
  Message,
  ArrowLeft,
  ArrowRight,
} from "@element-plus/icons-vue";
import Logo from "@/components/Logo.vue";
import BrandPanel from "@/views/StandAlone/Login/BrandPanel.vue";
import { readRememberPreference } from "@/utils/authStorage";
import { ElMessage } from "element-plus";

const router = useRouter();

/** 当前 Tab（纯静态切换） */
const activeTab = ref<"login" | "register">("login");

// 表单数据
// 「记住我」：勾选 → 登录态存 localStorage（关掉浏览器仍登录，后端签长期令牌）；
//            不勾 → 只存 sessionStorage（关掉浏览器需重新登录，后端签会话令牌）
// 默认值取上次登录时的选择，常见用户预期是「上次勾了这次还勾着」
const loginForm = reactive({
  account: "",
  password: "",
  remember: readRememberPreference(),
});
const registerForm = reactive({
  account: "",
  password: "",
  confirm: "",
});
const {
  login: doLogin,
  register: doRegister,
  loading: loginLoading,
} = useAuth();

// 登录提交
const onLogin = () => {
  doLogin({
    account: loginForm.account,
    password: loginForm.password,
    remember: loginForm.remember,
  });
};

// 注册提交
const onRegister = async () => {
  const { account, password, confirm } = registerForm;
  if (!account.trim() || !password) {
    ElMessage.warning("请填写账号和密码");
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
  await doRegister({ account: account.trim(), password });
};

// TODO: 第三方登录（GitHub OAuth / 微信扫码 / 邮箱验证码）
const onOAuth = (provider: "qq" | "wechat" | "email") => {
  console.log("oauth:", provider);
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

      <div class="form-title">欢迎使用</div>
      <div class="form-subtitle">登录以继续你的市场情报分析之旅</div>

      <!-- 登录 / 注册 Tab -->
      <div
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

      <!-- 登录表单（静态） -->
      <div v-show="activeTab === 'login'" class="form-body">
        <el-input
          v-model="loginForm.account"
          :prefix-icon="User"
          placeholder="请输入账号"
          size="large"
        />
        <el-input
          v-model="loginForm.password"
          :prefix-icon="Lock"
          type="password"
          show-password
          placeholder="请输入密码"
          size="large"
        />
        <div class="form-row">
          <el-checkbox
            v-model="loginForm.remember"
            title="勾选后关闭浏览器再打开仍是登录状态；不勾选则关闭浏览器后需要重新登录"
            >记住我</el-checkbox
          >
          <el-button class="form-link forgot-btn" link>忘记密码？</el-button>
        </div>
        <el-button
          class="submit-btn"
          type="primary"
          :loading="loginLoading"
          @click="onLogin"
        >
          登录
          <el-icon>
            <ArrowRight />
          </el-icon>
        </el-button>
      </div>

      <!-- 注册表单（静态） -->
      <div v-show="activeTab === 'register'" class="form-body">
        <el-input
          v-model="registerForm.account"
          :prefix-icon="User"
          placeholder="请输入账号"
          size="large"
        />
        <el-input
          v-model="registerForm.password"
          :prefix-icon="Lock"
          type="password"
          show-password
          placeholder="请输入密码"
          size="large"
        />
        <el-input
          v-model="registerForm.confirm"
          :prefix-icon="Lock"
          type="password"
          show-password
          placeholder="请再次输入密码"
          size="large"
        />
        <el-button class="submit-btn" type="primary" @click="onRegister">
          注册
        </el-button>
      </div>

      <!-- 第三方登录 -->
      <div class="divider"><span>其他登录方式</span></div>
      <div class="oauth-row">
        <button class="oauth-btn" @click="onOAuth('qq')">
          <svg viewBox="0 0 1024 1024" fill="#12B7F5">
            <path
              d="M824.8 613.2c-16-51.4-34.4-94.6-62.7-165.3C766.5 262.2 689.3 112 511.5 112 331.7 112 256.2 265.2 261 447.9c-28.4 70.8-46.7 113.7-62.7 165.3-34 109.5-23 154.8-14.6 155.8 18 2.2 70.1-82.4 70.1-82.4 0 49 25.2 112.9 79.8 159-26.4 8.1-85.7 29.9-71.6 53.8 11.4 19.3 196.2 12.3 249.5 6.3 53.3 6 238.1 13 249.5-6.3 14.1-23.8-45.3-45.7-71.6-53.8 54.6-46.2 79.8-110.1 79.8-159 0 0 52.1 84.6 70.1 82.4 8.5-1.1 19.5-46.4-14.5-155.8z"
              p-id="9486"
            ></path>
          </svg>
          QQ
        </button>

        <button class="oauth-btn" @click="onOAuth('wechat')">
          <svg viewBox="0 0 24 24" fill="#07C160">
            <path
              d="M9.5 4C5.9 4 3 6.5 3 9.6c0 1.8 1 3.4 2.5 4.4l-.6 2 2.2-1.1c.5.1 1 .2 1.6.2h.4A5.6 5.6 0 0 1 9 13.9C9 10.9 11.9 8.5 15.3 8.5h.4C15.1 5.9 12.6 4 9.5 4zM7.4 7.4a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8zm4.2 0a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8z"
            />
            <path
              d="M15.5 9.5c-3 0-5.5 2-5.5 4.5s2.5 4.5 5.5 4.5c.5 0 1-.1 1.5-.2l1.9 1-.5-1.8c1.4-.8 2.3-2.1 2.3-3.5 0-2.5-2.5-4.5-5.2-4.5zm-2 2.6a.8.8 0 1 1 0 1.5.8.8 0 0 1 0-1.5zm4 0a.8.8 0 1 1 0 1.5.8.8 0 0 1 0-1.5z"
            />
          </svg>
          微信
        </button>
        <button class="oauth-btn" @click="onOAuth('email')">
          <el-icon>
            <Message />
          </el-icon>
          邮箱
        </button>
      </div>

      <div class="form-footer">
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

.forgot-btn {
  font-size: 1vmax;
}

.form-body :deep(.el-checkbox__inner) {
  background-color: transparent;
  border: 1px solid color-mix(in oklch, var(--app-color-blue) 50%, transparent);
}

.form-body :deep(.el-checkbox.is-checked .el-checkbox__inner) {
  border-color: var(--app-color-blue);
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

.register-btn {
  font-size: 1vmax;
}

/* 分隔线 */
.divider {
  display: flex;
  align-items: center;
  gap: 1vw;
  font-size: 1vmax;
  color: var(--app-color-gray);
}

.divider::before,
.divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: color-mix(in oklch, var(--app-color-gray) 30%, transparent);
}

/* 第三方登录：用原生 button，避开 global.css 的 el-button 胶囊样式 */
.oauth-row {
  display: flex;
  gap: 1vw;
  margin-top: 1.5vh;
}

.oauth-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5vw;
  padding: 1vh 0;
  font-size: 1vmax;
  color: var(--app-color-black);
  background: none;
  border: 1px solid color-mix(in oklch, var(--app-color-blue) 50%, transparent);
  border-radius: 1vmax;
  cursor: pointer;
  transition: all 0.2s ease;
}

.oauth-btn:hover {
  border-color: var(--app-color-blue-light-2);
  background: var(--app-color-blue-light-5);
}

.oauth-btn:active {
  border-color: var(--app-color-blue);
  background: var(--app-color-blue-light-4);
}

.oauth-btn svg {
  width: 1.5em;
  height: 1.5em;
}

.form-footer {
  margin: 2vh 0 0;
  text-align: center;
  font-size: 1.2vmax;
  color: var(--app-text-color-secondary);
}
</style>
