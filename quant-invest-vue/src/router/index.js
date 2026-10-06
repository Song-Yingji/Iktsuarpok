import { createRouter, createWebHistory } from 'vue-router'
import { useApp } from '../store/app'

const routes = [
  { path: '/login', component: () => import('../pages/Login.vue') },
  { path: '/register', component: () => import('../pages/Register.vue') },
  { path: '/admin/login', component: () => import('../pages/AdminLogin.vue') },
  { path: '/admin', component: () => import('../pages/Admin.vue') },
  {
    path: '/',
    component: () => import('../components/Layout.vue'),
    children: [
      { path: '', redirect: '/market' },
      { path: 'market', component: () => import('../pages/Market.vue') },
      { path: 'watchlist', component: () => import('../pages/Watchlist.vue') },
      { path: 'news', component: () => import('../pages/News.vue') },
      { path: 'agents', component: () => import('../pages/Agents.vue') },
      { path: 'strategy', component: () => import('../pages/Strategy.vue') },
      { path: 'accounts', component: () => import('../pages/Accounts.vue') },
      { path: 'preferences', component: () => import('../pages/Preferences.vue') }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/market' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  // 后台与前台是两套独立登录态，各自校验各自的 token
  if (to.path.startsWith('/admin')) {
    const isLogin = to.path === '/admin/login'
    const adminToken = localStorage.getItem('admin_token')
    if (isLogin) return adminToken ? '/admin' : true
    return adminToken ? true : '/admin/login'
  }

  const { user } = useApp()
  if (!user.value && to.path !== '/login' && to.path !== '/register') {
    return '/login'
  }
  if (user.value && (to.path === '/login' || to.path === '/register')) {
    return '/market'
  }
  return true
})

export default router
