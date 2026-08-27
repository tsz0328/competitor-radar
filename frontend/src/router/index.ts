// 引入两个vue-router的函数
import { createRouter, createWebHistory } from "vue-router";

// 引入路由组件
import Landing from "@/views/StandAlone/Landing.vue";
import Login from "@/views/StandAlone/Login/Login.vue";

import AppLayout from "@/layouts/AppLayout/AppLayout.vue";

import Dashboard from "@/views/app/Dashboard.vue";
import Competitor from "@/views/app/Competitor.vue";
import Event from "@/views/app/Event.vue";
import Report from "@/views/app/Report.vue";
import Trend from "@/views/app/Trend.vue";
import Setting from "@/views/app/Setting.vue";


// 创建路由实例，传入一个配置对象
const router = createRouter({
    // 使用vue-router的createWebHistory函数创建一个路由历史记录
    history: createWebHistory(),
    // 定义路由规则
    routes: [
        {
            path: "/",
            component: Landing,
            name: "Landing"
        },
        {
            path: "/login",
            component: Login,
            name: "Login"
        },
        {
            path: "/app",
            component: AppLayout,
            name: "AppLayout",
            redirect: { name: "Dashboard" },
            children: [
                {
                    path: "dashboard",
                    component: Dashboard,
                    name: "Dashboard"
                },
                {
                    path: "competitor",
                    component: Competitor,
                    name: "Competitor"
                },
                {
                    path: "event",
                    component: Event,
                    name: "Event"
                },
                {
                    path: "report",
                    component: Report,
                    name: "Report"
                },
                {
                    path: "trend",
                    component: Trend,
                    name: "Trend"
                },
                {
                    path: "setting",
                    component: Setting,
                    name: "Setting"
                }
            ]
        }
    ]
})

router.beforeEach((to) => {
  const token = localStorage.getItem("token");
  if (to.path !== "/login" && to.path !== "/" && !token) {
    return "/login";
  }
});


// 导出路由实例
export default router;