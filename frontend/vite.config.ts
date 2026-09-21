import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { viteMockServe } from "vite-plugin-mock";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [
    vue(),
    viteMockServe({
      mockPath: "mock", //指向 frontend/mock 目录
      enable: true, //开发环境启用 mock（无后端也可完整使用）；生产构建自动关闭
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
    // 后端就绪时，把 enable 设为 false 即可恢复 proxy 转发
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
