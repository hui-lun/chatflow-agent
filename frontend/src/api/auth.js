import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

// 建立 axios 實例
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 請求攔截器 - 自動加入 token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 回應攔截器 - 處理認證錯誤
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    if (error.response?.status === 401) {
      // Token 無效，清除本地儲存並重新導向登入頁面
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// 登入 API
export const login = async (username, password) => {
  const response = await api.post('/auth/login', {
    username,
    password,
  })
  return response.data
}

// 取得當前使用者資訊
export const getCurrentUser = async () => {
  const response = await api.get('/auth/me')
  return response.data
}

// 登出函數
export const logout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  window.location.href = '/login'
}

// 檢查是否已登入
export const isAuthenticated = () => {
  return !!localStorage.getItem('token')
}

// 取得儲存的使用者名稱
export const getStoredUsername = () => {
  return localStorage.getItem('username')
} 