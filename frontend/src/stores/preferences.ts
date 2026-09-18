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
  const loaded = ref(false);
  let inflight: Promise<void> | null = null;

  async function load() {
    try {
      const prefs = await fetchMyPreferences();
      allowUnreachableOfficial.value = prefs.allowUnreachableOfficial;
      if (prefs.defaultSourceTypes.length) {
        defaultSourceTypes.value = prefs.defaultSourceTypes;
      }
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
  }) {
    const prefs = await saveMyPreferences(patch);
    allowUnreachableOfficial.value = prefs.allowUnreachableOfficial;
    if (prefs.defaultSourceTypes.length) {
      defaultSourceTypes.value = prefs.defaultSourceTypes;
    }
    return prefs;
  }

  return {
    allowUnreachableOfficial,
    defaultSourceTypes,
    loaded,
    ensureLoaded,
    save,
  };
});
