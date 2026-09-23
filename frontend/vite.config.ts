import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import { viteMockServe } from "vite-plugin-mock";
import { fileURLToPath, URL } from "node:url";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // 仅开发环境用 mock；生产构建始终关闭（command === "build" 时即使 VITE_USE_MOCK=true 也不生效）
  // VITE_USE_MOCK=true  → /api 走前端 mock，完全脱离后端
  // VITE_USE_MOCK=false → /api 经 proxy 转发到真实后端 localhost:8000
  const useMock = env.VITE_USE_MOCK === "true" && command === "serve";

  return {
    plugins: [
      vue(),
      viteMockServe({
        mockPath: "mock", //指向 frontend/mock 目录
        enable: useMock,
      }),
    ],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    build: {
      rollupOptions: {
        output: {
          // 把稳定的大型依赖拆成独立 chunk，避免业务改动再次生成同一个 1.7MB 入口文件
          manualChunks: {
            "vue-vendor": ["vue", "vue-router", "pinia"],
            "element-plus": ["element-plus", "@element-plus/icons-vue"],
            echarts: ["echarts", "vue-echarts"],
            axios: ["axios"],
            markdown: ["marked", "dompurify"],
          },
        },
      },
    },
    server: {
      port: 5173,
      // 注意：开了 mock 后，/api 会被 mock 拦截，不会再转发到 8000
      // 后端就绪时，把 .env.development 里 VITE_USE_MOCK 设为 false 即可恢复 proxy 转发
      proxy: {
        "/api": { target: "http://localhost:8000", changeOrigin: true },
      },
    },
  };
});