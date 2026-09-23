import { ref } from "vue";
import { defineStore } from "pinia";
import { fetchMyPreferences, saveMyPreferences } from "@/api/user";

/**
 * 用户级偏好：跟账号走，存服务端。
 * 原先放在 localStorage，换浏览器/换设备就丢了，也不属于账号。
 */
export const usePreferencesStore = defineStore("preferences", () => {
  const allowUnreachableOfficial = ref(false);
  // 后端未设置过时返回空数组，这里给一个稳妥的默认值（只看官网首页）
  const defaultSourceTypes = ref<string[]>(["homepage"]);
  // 是否接收邮件通知（默认开启）；关闭后高优事件 / 抓取汇总 / 周报不发邮件
  const emailNotifyEnabled = ref(true);
  const loaded = ref(false);
  let inflight: Promise<void> | null = null;

  async function load() {
    try {
      const prefs = await fetchMyPreferences();
      allowUnreachableOfficial.value = prefs.allowUnreachableOfficial;
      if (prefs.defaultSourceTypes.length) {
        defaultSourceTypes.value = prefs.defaultSourceTypes;
      }
      emailNotifyEnabled.value = prefs.emailNotifyEnabled;
    } catch {
      // 失败时保留默认值，不阻塞页面
    } finally {
      loaded.value = true;
    }
  }

  /** 幂等加载：多个组件同时用到偏好时只打一次接口 */
  function ensureLoaded(): Promise<void> {
    if (loaded.value) return Promise.resolve();
    inflight ??= load();
    return inflight;
  }

  /** 局部保存：成功后用服务端返回值回填，保证本地与服务端一致 */
  async function save(patch: {
    allowUnreachableOfficial?: boolean;
    defaultSourceTypes?: string[];
    emailNotifyEnabled?: boolean;
  }) {
    const prefs = await saveMyPreferences(patch);
    allowUnreachableOfficial.value = prefs.allowUnreachableOfficial;
    if (prefs.defaultSourceTypes.length) {
      defaultSourceTypes.value = prefs.defaultSourceTypes;
    }
    emailNotifyEnabled.value = prefs.emailNotifyEnabled;
    return prefs;
  }

  return {
    allowUnreachableOfficial,
    defaultSourceTypes,
    emailNotifyEnabled,
    loaded,
    ensureLoaded,
    save,
  };
});
