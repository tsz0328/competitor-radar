import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { viteMockServe } from "vite-plugin-mock";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [
    vue(),
    viteMockServe({
      mockPath: "mock", //指向 frontend/mock 目录
      enable: true, //开发环境启用；生产构建自动关闭
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
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
