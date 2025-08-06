<template>
  <div class="chat-container">
    <div class="chat-header">
      <div class="header-left">
        <h2>ChatFlow Agent</h2>
        <span class="user-info">歡迎，{{ username }}</span>
      </div>
      <div class="header-right">
        <div class="session-controls">
          <select v-model="currentSession" @change="loadChatHistory">
            <option v-for="session in displaySessions" :key="session.value" :value="session.value">
              {{ session.label }}
            </option>
          </select>
          <button @click="createNewSession" class="new-session-btn">New Chat</button>
        </div>
        <button @click="handleLogout" class="logout-btn">登出</button>
      </div>
    </div>
    
    <div class="chat-messages" ref="messagesContainer">
      <div v-for="(msg, idx) in messages" :key="idx" :class="['chat-message', msg.role]">
        <div class="message-header">
          <span class="role-label">{{ msg.role === 'user' ? 'You' : 'Bot' }}</span>
          <span class="timestamp" v-if="msg.timestamp">{{ formatTimestamp(msg.timestamp) }}</span>
        </div>
        <div class="message-content">{{ msg.content }}</div>
      </div>
      <div v-if="loading" class="chat-message bot loading">
        <div class="message-content">Thinking...</div>
      </div>
    </div>
    
    <form class="chat-input" @submit.prevent="sendMessage">
      <input 
        v-model="input" 
        type="text" 
        placeholder="Type your message..." 
        :disabled="loading"
      />
      <button type="submit" :disabled="loading || !input.trim()">Send</button>
    </form>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { sendChat, getChatHistory, getAllSessions } from '../api/chat'
import { logout, getStoredUsername } from '../api/auth'
import '../assets/styles/main.scss'

const input = ref('')
const messages = ref([])
const loading = ref(false)
const currentSession = ref('default')
const sessions = ref([])
const displaySessions = ref([])
const messagesContainer = ref(null)
const username = ref('')

// 載入聊天歷史
const loadChatHistory = async () => {
  try {
    const history = await getChatHistory(currentSession.value)
    messages.value = history.map(item => [
      { role: 'user', content: item.user_message, timestamp: item.timestamp },
      { role: 'bot', content: item.bot_response, timestamp: item.timestamp }
    ]).flat()
    scrollToBottom()
  } catch (error) {
    console.error('Failed to load chat history:', error)
  }
}

// 載入所有會話
const loadSessions = async () => {
  try {
    sessions.value = await getAllSessions()
    updateDisplaySessions()
  } catch (error) {
    console.error('Failed to load sessions:', error)
  }
}

// 更新顯示的會話列表
const updateDisplaySessions = () => {
  const sessionList = sessions.value || []
  
  // 確保至少有一個 default session
  if (sessionList.length === 0 || !sessionList.includes('default')) {
    sessionList.unshift('default')
  }
  
  // 轉換為顯示格式，default session 顯示為 "Default Session"
  displaySessions.value = sessionList.map(session => ({
    value: session,
    label: session === 'default' ? 'Default Session' : session
  }))
}

// 創建新會話
const createNewSession = () => {
  const newSessionId = `session_${Date.now()}`
  currentSession.value = newSessionId
  messages.value = []
  // 立即更新顯示列表包含新會話
  if (!sessions.value.includes(newSessionId)) {
    sessions.value.push(newSessionId)
    updateDisplaySessions()
  }
}

// 發送訊息
const sendMessage = async () => {
  if (!input.value.trim() || loading.value) return
  
  const userMsg = { role: 'user', content: input.value.trim() }
  messages.value.push(userMsg)
  
  const userInput = input.value.trim()
  input.value = ''
  loading.value = true
  
  try {
    const response = await sendChat(userInput, currentSession.value)
    messages.value.push({ 
      role: 'bot', 
      content: response.response, 
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    messages.value.push({ 
      role: 'bot', 
      content: `Error: ${error.message || 'Failed to get response'}` 
    })
  } finally {
    loading.value = false
    await nextTick()
    scrollToBottom()
  }
}

// 滾動到底部
const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// 格式化時間戳
const formatTimestamp = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString()
}

// 登出處理
const handleLogout = () => {
  logout()
}

// 組件掛載時載入資料
onMounted(async () => {
  username.value = getStoredUsername() || 'User'
  await loadSessions()
  await loadChatHistory()
})
</script>

 