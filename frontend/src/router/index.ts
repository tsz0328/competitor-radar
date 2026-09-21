// 引入两个vue-router的函数
import {
  createRouter,
  createWebHistory,
  type RouterScrollBehavior,
} from "vue-router";
import { readToken, isTokenExpired } from "@/utils/authStorage";

// 引入路由组件
const Landing = () => import("@/views/StandAlone/Landing.vue");
const Login = () => import("@/views/StandAlone/Login/Login.vue");
// 文档页：隐私政策 / 服务条款 / 使用文档共用一个组件，靠 meta.doc 区分
const Docs = () => import("@/views/StandAlone/Docs.vue");

const AppLayout = () => import("@/layouts/AppLayout/AppLayout.vue");

const Dashboard = () => import("@/views/app/Dashboard.vue");
const Competitor = () => import("@/views/app/Competitor.vue");
const CrawlLog = () => import("@/views/app/CrawlLog.vue");
const Event = () => import("@/views/app/Event.vue");
const Report = () => import("@/views/app/Report.vue");
const Trend = () => import("@/views/app/Trend.vue");
const Setting = () => import("@/views/app/Setting.vue");
const UserManage = () => import("@/views/app/UserManage.vue");
const AdminCompetitors = () => import("@/views/app/AdminCompetitors.vue");
const Trash = () => import("@/views/app/Trash.vue");


/**
 * 滚动行为：必须写在 createRouter 的配置里 —— vue-router 是在导航时从
 * options 读的，事后挂 `router.scrollBehavior = ...` 不生效。
 *
 * 不配置的话，SPA 换页会保留上一页的滚动位置：在文档页读到一半切到隐私政策，
 * 会停在长文的半中间，看起来像"切过去是空的"。
 */
const HASH_OFFSET = 80; // 锚点跳转时给顶部留出的高度
const scrollBehavior: RouterScrollBehavior = (to, from, savedPosition) => {
  // 浏览器前进 / 后退：回到原来的位置
  if (savedPosition) return savedPosition;
  // 带锚点（文档目录 #sec-2、落地页页脚 #features 等）：滚到对应元素
  if (to.hash) return { el: to.hash, top: HASH_OFFSET, behavior: "smooth" };
  // 同一页面只改 query（如情报中心的筛选）：不要动滚动位置
  if (to.path === from.path) return false;
  // 换页面：回到顶部
  return { top: 0 };
};

// 创建路由实例，传入一个配置对象
const router = createRouter({
    // 使用vue-router的createWebHistory函数创建一个路由历史记录
    history: createWebHistory(),
    scrollBehavior,
    // 定义路由规则
    routes: [
        {
            path: "/",
            component: Landing,
            name: "Landing",
            // public：未登录也能访问（路由守卫据此放行）
            meta: { public: true }
        },
        {
            path: "/login",
            component: Login,
            name: "Login",
            meta: { public: true }
        },
        {
            path: "/privacy",
            component: Docs,
            name: "Privacy",
            meta: { public: true, doc: "privacy" }
        },
        {
            path: "/terms",
            component: Docs,
            name: "Terms",
            meta: { public: true, doc: "terms" }
        },
        {
            // 使用文档：落地页页脚与登录后顶栏的「?」都指过来
            path: "/help",
            component: Docs,
            name: "Help",
            meta: { public: true, doc: "guide" }
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
                    path: "crawl-log",
                    component: CrawlLog,
                    name: "CrawlLog"
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
                    path: "trash",
                    component: Trash,
                    name: "Trash"
                },
                {
                    path: "setting",
                    component: Setting,
                    name: "Setting"
                },
                {
                    path: "user-manage",
                    component: UserManage,
                    name: "UserManage"
                },
                {
                    path: "all-competitors",
                    component: AdminCompetitors,
                    name: "AdminCompetitors"
                }
            ]
        }
    ]
})

router.beforeEach((to) => {
  // 公开页（落地页 / 登录 / 隐私政策 / 服务条款）不需要登录：
  // 用路由 meta.public 声明，避免每加一个页面都要回来改这里的硬编码路径
  if (to.meta.public) return;
  // token 可能在 localStorage（记住我）或 sessionStorage（仅本次会话）
  // 没有 token，或 token 已过期 → 直接去登录。
  // 验 exp 是为了消除「带着过期 token 先进 /app，渲染完才被后端 401 踢」的闪烁；
  // 解析不出 exp 时 isTokenExpired 返回 false，仍由后端 401 兜底。
  if (!readToken() || isTokenExpired()) return "/login";
});




// 导出路由实例
export default router;
