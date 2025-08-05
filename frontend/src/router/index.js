import { createRouter, createWebHistory } from 'vue-router'
import { isAuthenticated } from '../api/auth'
import Login from '../views/Login.vue'
import Chat from '../views/Chat.vue'

const routes = [
  {
    path: '/',
    redirect: '/chat'
  },
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { requiresAuth: false }
  },
  {
    path: '/chat',
    name: 'Chat',
    component: Chat,
    meta: { requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守衛
router.beforeEach((to, from, next) => {
  const requiresAuth = to.meta.requiresAuth !== false
  
  if (requiresAuth && !isAuthenticated()) {
    // 需要認證但未登入，導向登入頁面
    next('/login')
  } else if (to.path === '/login' && isAuthenticated()) {
    // 已登入但訪問登入頁面，導向聊天頁面
    next('/chat')
  } else {
    next()
  }
})

export default router 