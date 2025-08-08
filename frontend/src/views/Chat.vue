<template>
  <div class="app-layout">
    <!-- Left Sidebar -->
    <div class="sidebar">
      <div class="sidebar-header">
        <h3>對話紀錄</h3>
        <button 
          @click="createNewSession" 
          :disabled="displaySessions.length === 0"
          class="new-chat-btn"
          :title="displaySessions.length === 0 ? '請先發送訊息開始對話' : '創建新對話'"
        >
          + New Chat
        </button>
      </div>
      
      <div class="sessions-list">
        <div v-if="displaySessions.length === 0" class="empty-state">
          <div class="empty-icon">💬</div>
          <div class="empty-text">尚無對話紀錄</div>
          <div class="empty-hint">發送訊息開始第一個對話</div>
        </div>
        <div 
          v-for="session in displaySessions" 
          :key="session.value" 
          :class="['session-item', { active: currentSession === session.value }]"
          @click="switchSession(session.value)"
        >
          <div class="session-info">
            <span class="session-name">{{ session.label }}</span>
          </div>
          <button 
            @click.stop="confirmDeleteSession(session.value)"
            class="delete-btn"
            title="刪除對話"
          >
            🗑️
          </button>
        </div>
      </div>
      
      <div class="sidebar-footer">
        <div class="user-info">{{ username }}</div>
        <button @click="handleLogout" class="logout-btn">登出</button>
      </div>
    </div>
    
    <!-- Main Chat Area -->
    <div class="main-content">
      <!-- RAG Controls -->
      <div class="rag-controls">
        <div class="rag-row">
          <label><input type="checkbox" v-model="useRAG" /> 啟用 RAG</label>
        </div>
        <div class="rag-row">
          <input v-model="ragCollection" placeholder="Collection 名稱 (e.g., shared_rag_collection)" />
          <input v-model="ragUserId" placeholder="User ID (e.g., user_A)" />
          <button @click="toggleRagUpload" class="small-btn">{{ showRagUpload ? '隱藏上傳' : '上傳 PDF' }}</button>
        </div>
        <div v-if="showRagUpload" class="rag-row">
          <input type="file" multiple accept="application/pdf" @change="onPdfSelected" />
          <input v-model.number="ragChunkSize" type="number" min="100" step="100" placeholder="chunk_size (預設 1000)" />
          <input v-model.number="ragChunkOverlap" type="number" min="0" step="50" placeholder="chunk_overlap (預設 200)" />
          <button @click="indexSelectedPdfs" :disabled="!canIndex" class="small-btn">建立索引</button>
          <span v-if="ragIndexing" class="rag-status">索引中...</span>
        </div>
      </div>
      <!-- Hidden select for maintaining existing logic -->
      <select v-model="currentSession" @change="loadChatHistory" style="display: none;">
        <option v-for="session in displaySessions" :key="session.value" :value="session.value">
          {{ session.label }}
        </option>
      </select>
      
      <div class="chat-messages" ref="messagesContainer">
        <div v-if="messages.length === 0 && !loading" class="chat-empty-state">
          <div class="welcome-icon">🤖</div>
          <h3>歡迎使用 ChatFlow Agent</h3>
          <p>在下方輸入框中輸入訊息開始對話</p>
        </div>
        <div v-for="(msg, idx) in messages" :key="idx" :class="['chat-message', msg.role]">
          <div class="message-header">
            <span class="role-label">{{ msg.role === 'user' ? 'You' : 'Bot' }}</span>
            <span class="timestamp" v-if="msg.timestamp">{{ formatTimestamp(msg.timestamp) }}</span>
          </div>
          <div class="message-content">{{ msg.content }}</div>
          <div v-if="msg.search_sources && msg.search_sources.length > 0" class="search-sources">
            <div class="sources-label">+ Sources:</div>
            <div class="sources-list">
              <a v-for="(source, sourceIdx) in msg.search_sources" 
                 :key="sourceIdx" 
                 :href="source" 
                 target="_blank" 
                 class="source-link">
                {{ source }}
              </a>
            </div>
          </div>
        </div>
        <div v-if="loading" class="chat-message bot loading">
          <div class="message-content">Thinking...</div>
        </div>
      </div>
      
      <form class="chat-input" @submit.prevent="sendMessage">
        <div class="input-wrapper">
          <!-- Web Search 標籤 -->
          <div v-if="useWebSearch" class="web-search-tag">
            <span class="tag-icon">🔍</span>
            <span class="tag-text">Web Search</span>
            <!-- 取消 Web Search 按鈕 -->
            <button 
              type="button" 
              @click="cancelWebSearch" 
              class="tag-cancel-btn"
              title="Cancel web search"
            >
              ×
            </button>
          </div>
          
          <input 
            v-model="input" 
            type="text" 
            :placeholder="useWebSearch ? 'Search the web and chat...' : (useRAG ? 'Ask with RAG...' : 'Type your message...')"
            :disabled="loading"
            :class="{ 'web-search-mode': useWebSearch }"
          />
          
          <!-- 加號按鈕 -->
          <button 
            type="button" 
            @click="toggleWebSearchMenu" 
            class="plus-btn"
            :class="{ active: showWebSearchMenu }"
            title="Add web search"
          >
            +
          </button>
          
          <!-- Dropdown menu -->
          <div 
            v-if="showWebSearchMenu" 
            class="web-search-dropdown"
          >
            <div class="dropdown-item" @click="toggleWebSearch">
              <span class="dropdown-icon">🔍</span>
              <span class="dropdown-text">Web Search</span>
              <span v-if="useWebSearch" class="dropdown-check">✓</span>
            </div>
          </div>
        </div>
        <button type="submit" :disabled="loading || !input.trim()">
          {{ loading ? (useWebSearch ? 'Searching' : 'Sending') : 'Send' }}
        </button>
      </form>
    </div>
    
    <!-- Delete Confirmation Modal -->
    <div v-if="showDeleteConfirm" class="modal-overlay" @click="cancelDelete">
      <div class="modal-content" @click.stop>
        <h4>確認刪除</h4>
        <p>確定要刪除這個對話嗎？此操作無法復原。</p>
        <div class="modal-actions">
          <button @click="cancelDelete" class="cancel-btn">取消</button>
          <button @click="executeDelete" class="confirm-btn">刪除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import { sendChat, sendWebSearchChat, getChatHistory, getAllSessions, deleteSession } from '../api/chat'
import { logout, getStoredUsername } from '../api/auth'
import { ragIndex, ragQuery } from '../api/rag'
import '../assets/styles/main.scss'

const input = ref('')
const messages = ref([])
const loading = ref(false)
const currentSession = ref(null)
const sessions = ref([])
const displaySessions = ref([])
const messagesContainer = ref(null)
const username = ref('')
const showDeleteConfirm = ref(false)
const sessionToDelete = ref(null)
const useWebSearch = ref(false)
const showWebSearchMenu = ref(false)
// RAG state
const useRAG = ref(false)
const ragCollection = ref('shared_rag_collection')
const ragUserId = ref('user_A')
const ragFiles = ref([])
const showRagUpload = ref(false)
const ragChunkSize = ref(1000)
const ragChunkOverlap = ref(200)
const ragIndexing = ref(false)
const canIndex = computed(() => useRAG.value && ragCollection.value && ragUserId.value && ragFiles.value.length > 0)

// 載入聊天歷史
const loadChatHistory = async () => {
  try {
    // 如果沒有當前會話，清空訊息
    if (!currentSession.value) {
      messages.value = []
      return
    }
    
    const history = await getChatHistory(currentSession.value)
    messages.value = history.map(item => [
      { role: 'user', content: item.user_message, timestamp: item.timestamp },
      { role: 'bot', content: item.bot_response, timestamp: item.timestamp }
    ]).flat()
    scrollToBottom()
  } catch (error) {
    console.error('Failed to load chat history:', error)
    messages.value = []
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
  
  // 直接轉換為顯示格式，不強制添加 default session
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

// 切換 web search 模式
const toggleWebSearch = () => {
  useWebSearch.value = !useWebSearch.value
  showWebSearchMenu.value = false // 選擇後關閉選單
}

// 切換 web search 選單顯示
const toggleWebSearchMenu = () => {
  showWebSearchMenu.value = !showWebSearchMenu.value
}

// 關閉 web search 選單 (點擊外部時)
const closeWebSearchMenu = () => {
  showWebSearchMenu.value = false
}

// 取消 Web Search 模式
const cancelWebSearch = () => {
  useWebSearch.value = false
  showWebSearchMenu.value = false
}

// RAG controls
const toggleRagUpload = () => { showRagUpload.value = !showRagUpload.value }
const onPdfSelected = (e) => { ragFiles.value = Array.from(e.target.files || []) }
const indexSelectedPdfs = async () => {
  if (!canIndex.value) return
  ragIndexing.value = true
  try {
    const res = await ragIndex({
      collection: ragCollection.value,
      userId: ragUserId.value,
      files: ragFiles.value,
      chunkSize: ragChunkSize.value,
      chunkOverlap: ragChunkOverlap.value,
    })
    alert(`索引完成：${res.points_upserted} points`)
    ragFiles.value = []
  } catch (e) {
    alert(`索引失敗：${e?.message || e}`)
  } finally {
    ragIndexing.value = false
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
    // 動態創建會話 - 如果沒有當前會話，創建新的
    let sessionId = currentSession.value
    if (!sessionId) {
      sessionId = `session_${Date.now()}`
      currentSession.value = sessionId
      
      // 將新會話加入列表
      sessions.value.push(sessionId)
      updateDisplaySessions()
    }
    
    // 根據模式選擇不同的API調用
    let response
    if (useWebSearch.value) {
      response = await sendWebSearchChat(userInput, sessionId)
    } else if (useRAG.value) {
      if (!ragCollection.value || !ragUserId.value) {
        throw new Error('請先設定 Collection 與 User ID')
      }
      const ragRes = await ragQuery({ message: userInput, collection: ragCollection.value, userId: ragUserId.value, limit: 5 })
      response = { response: ragRes.response }
    } else {
      response = await sendChat(userInput, sessionId)
    }
    
    const botMsg = { 
      role: 'bot', 
      content: response.response, 
      timestamp: new Date().toISOString()
    }
    
    // 如果有搜索來源，添加到消息中
    if (response.search_sources && response.search_sources.length > 0) {
      botMsg.search_sources = response.search_sources
    }
    
    messages.value.push(botMsg)
    
    // 確保會話在列表中（處理後端可能改變 session ID 的情況）
    if (response.session_id && response.session_id !== sessionId) {
      currentSession.value = response.session_id
      if (!sessions.value.includes(response.session_id)) {
        sessions.value.push(response.session_id)
        updateDisplaySessions()
      }
    }
    
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

// 切換會話
const switchSession = (sessionId) => {
  if (currentSession.value !== sessionId) {
    currentSession.value = sessionId
    loadChatHistory()
  }
}

// 確認刪除會話
const confirmDeleteSession = (sessionId) => {
  sessionToDelete.value = sessionId
  showDeleteConfirm.value = true
}

// 取消刪除
const cancelDelete = () => {
  showDeleteConfirm.value = false
  sessionToDelete.value = null
}

// 執行刪除
const executeDelete = async () => {
  if (!sessionToDelete.value) return
  
  try {
    await deleteSession(sessionToDelete.value)
    
    // 從本地列表中移除會話
    sessions.value = sessions.value.filter(s => s !== sessionToDelete.value)
    updateDisplaySessions()
    
    // 如果刪除的是當前會話，切換到其他可用會話或清空當前會話
    if (currentSession.value === sessionToDelete.value) {
      if (sessions.value.length > 0) {
        // 切換到剩餘的第一個會話
        currentSession.value = sessions.value[0]
        await loadChatHistory()
      } else {
        // 如果沒有其他會話，回到初始空狀態
        currentSession.value = null
        messages.value = []
      }
    }
    
    showDeleteConfirm.value = false
    sessionToDelete.value = null
    
    console.log('Session deleted successfully')
  } catch (error) {
    console.error('Failed to delete session:', error)
    alert('刪除對話失敗，請稍後再試')
    cancelDelete()
  }
}

// 登出處理
const handleLogout = () => {
  logout()
}

// 組件掛載時載入資料
onMounted(async () => {
  username.value = getStoredUsername() || 'User'
  await loadSessions()
  // 如果有會話且沒有當前選中的會話，選中第一個
  if (displaySessions.value.length > 0 && !currentSession.value) {
    currentSession.value = displaySessions.value[0].value
    await loadChatHistory()
  } else {
    // 否則確保聊天區域是空的
    messages.value = []
  }
  
  // 添加點擊外部關閉選單的事件監聽器
  document.addEventListener('click', (event) => {
    const inputWrapper = event.target.closest('.input-wrapper')
    const dropdown = event.target.closest('.web-search-dropdown')
    if (!inputWrapper && !dropdown && showWebSearchMenu.value) {
      closeWebSearchMenu()
    }
  })
  
})
</script>

<style scoped>
.rag-controls { margin-bottom: 10px; }
.rag-row { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
.small-btn { padding: 6px 10px; font-size: 12px; }
.rag-status { font-size: 12px; color: #666; }
</style>

 