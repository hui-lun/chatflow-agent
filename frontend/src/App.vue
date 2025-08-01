<template>
  <div class="chat-container">
    <div class="chat-header">
      <h2>ChatFlow Agent</h2>
      <div class="session-controls">
        <select v-model="currentSession" @change="loadChatHistory">
          <option value="default">Default Session</option>
          <option v-for="session in sessions" :key="session" :value="session" v-if="session !== 'default'">
            {{ session }}
          </option>
        </select>
        <button @click="createNewSession" class="new-session-btn">New Session</button>
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
import { sendChat, getChatHistory, getAllSessions } from './api/chat'
import './assets/styles/main.scss'

const input = ref('')
const messages = ref([])
const loading = ref(false)
const currentSession = ref('default')
const sessions = ref([])
const messagesContainer = ref(null)

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
  } catch (error) {
    console.error('Failed to load sessions:', error)
  }
}

// 創建新會話
const createNewSession = () => {
  const newSessionId = `session_${Date.now()}`
  currentSession.value = newSessionId
  messages.value = []
  loadSessions()
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

// 組件掛載時載入資料
onMounted(async () => {
  await loadSessions()
  await loadChatHistory()
})
</script> 