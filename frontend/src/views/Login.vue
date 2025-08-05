<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1>ChatFlow Agent</h1>
        <p>內部系統登入</p>
      </div>
      
      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label for="username">帳號</label>
          <input
            id="username"
            v-model="username"
            type="text"
            placeholder="請輸入帳號"
            required
            :disabled="loading"
          />
        </div>
        
        <div class="form-group">
          <label for="password">密碼</label>
          <input
            id="password"
            v-model="password"
            type="password"
            placeholder="請輸入密碼"
            required
            :disabled="loading"
          />
        </div>
        
        <div v-if="error" class="error-message">
          {{ error }}
        </div>
        
        <button type="submit" :disabled="loading || !username || !password" class="login-btn">
          <span v-if="loading">登入中...</span>
          <span v-else>登入</span>
        </button>
      </form>
      
      <div class="demo-accounts">
        <h3>測試帳號</h3>
        <div class="account-list">
          <div class="account-item">
            <strong>admin</strong> / admin123
          </div>
          <div class="account-item">
            <strong>user1</strong> / user123
          </div>
          <div class="account-item">
            <strong>user2</strong> / user456
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login } from '../api/auth'
import '../assets/styles/main.scss'

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

const handleLogin = async () => {
  if (!username.value || !password.value) return
  
  loading.value = true
  error.value = ''
  
  try {
    const response = await login(username.value, password.value)
    
    // 儲存 token 和使用者資訊
    localStorage.setItem('token', response.access_token)
    localStorage.setItem('username', response.username)
    
    // 導向聊天頁面
    router.push('/chat')
  } catch (err) {
    error.value = err.response?.data?.detail || '登入失敗，請檢查帳號密碼'
  } finally {
    loading.value = false
  }
}
</script>

 