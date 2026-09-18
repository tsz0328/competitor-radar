// 引入两个vue-router的函数
import { createRouter, createWebHistory } from "vue-router";

// 引入路由组件
const Landing = () => import("@/views/StandAlone/Landing.vue");
const Login = () => import("@/views/StandAlone/Login/Login.vue");

const AppLayout = () => import("@/layouts/AppLayout/AppLayout.vue");

const Dashboard = () => import("@/views/app/Dashboard.vue");
const Competitor = () => import("@/views/app/Competitor.vue");
const Event = () => import("@/views/app/Event.vue");
const Report = () => import("@/views/app/Report.vue");
const Trend = () => import("@/views/app/Trend.vue");
const Setting = () => import("@/views/app/Setting.vue");


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
