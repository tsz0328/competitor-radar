import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'        // 引入element-plus默认样式
import VueEcharts from 'vue-echarts'
import * as echarts from 'echarts'

import './styles/global.css'                // 全局样式覆盖

import App from './App.vue'
import router from './router'
import { setupBrowserMock } from '@/mock/browser'

// 纯前端演示部署（VITE_USE_MOCK=true）时，用浏览器端 mock 接管 /api 请求，无需后端
async function bootstrap() {
  if (import.meta.env.VITE_USE_MOCK === 'true') {
    await setupBrowserMock()
  }

  // 创建应用app
  const app = createApp(App)

  app.use(createPinia())
  app.use(router)
  app.use(ElementPlus)
  app.component('vue-echarts', VueEcharts)

  // 挂载到id为app的元素上
  app.mount('#app')
}

bootstrap()
