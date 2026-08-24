import {
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
} from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// 路由元信息类型扩展
declare module 'vue-router' {
  interface RouteMeta {
    /** 页面标题 */
    title?: string
    /** 是否公开访问（无需登录） */
    public?: boolean
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: () => import('@/views/LayoutView.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '总览仪表盘' },
      },
      {
        path: 'servers',
        name: 'ServerList',
        component: () => import('@/views/ServerListView.vue'),
        meta: { title: '服务器监控' },
      },
      {
        path: 'servers/:host',
        name: 'ServerDetail',
        component: () => import('@/views/ServerDetailView.vue'),
        meta: { title: '服务器详情' },
      },
      {
        path: 'logs',
        name: 'LogQuery',
        component: () => import('@/views/LogQueryView.vue'),
        meta: { title: '日志查询' },
      },
      {
        path: 'services',
        name: 'ServiceList',
        component: () => import('@/views/ServiceListView.vue'),
        meta: { title: '应用服务' },
      },
      {
        path: 'configs',
        name: 'ConfigEdit',
        component: () => import('@/views/ConfigEditView.vue'),
        meta: { title: '配置管理' },
      },
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/ChatView.vue'),
        meta: { title: 'AI 运维对话' },
      },
      {
        path: 'local-configs',
        name: 'LocalConfigs',
        component: () => import('@/views/LocalConfigView.vue'),
        meta: { title: '本地配置管理' },
      },
      {
        path: 'parameters',
        name: 'Parameters',
        component: () => import('@/views/ParameterView.vue'),
        meta: { title: '参数管理' },
      },
      {
        path: 'alerts',
        name: 'Alerts',
        component: () => import('@/views/AlertView.vue'),
        meta: { title: '告警管理' },
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/KnowledgeView.vue'),
        meta: { title: '知识库管理' },
      },
      {
        path: 'heal-rules',
        name: 'HealRules',
        component: () => import('@/views/HealRulesView.vue'),
        meta: { title: '自愈规则管理' },
      },
      {
        path: 'skills',
        name: 'Skills',
        component: () => import('@/views/SkillsView.vue'),
        meta: { title: '技能目录' },
      },
      {
        path: 'mcp',
        name: 'Mcp',
        component: () => import('@/views/McpView.vue'),
        meta: { title: 'MCP 工具' },
      },
      {
        path: 'topology',
        name: 'Topology',
        component: () => import('@/views/TopologyView.vue'),
        meta: { title: '拓扑管理' },
      },
      {
        path: 'audit',
        name: 'Audit',
        component: () => import('@/views/AuditView.vue'),
        meta: { title: '审计日志' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    redirect: '/dashboard',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局前置守卫：无 token 则跳转登录
router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    next()
    return
  }
  if (!auth.token) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  next()
})

export default router
