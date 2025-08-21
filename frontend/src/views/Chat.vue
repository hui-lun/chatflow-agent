<template>
  <div class="app-layout">
    <!-- Navigation Bar -->
    <div class="nav-bar">
      <div class="nav-tabs">
        <router-link to="/chat" class="nav-tab active">
          <span class="nav-icon">💬</span>
          對話
        </router-link>
        <router-link to="/kb" class="nav-tab">
          <span class="nav-icon">📚</span>
          知識庫
        </router-link>
      </div>
      <div class="user-info-nav">
        <span>{{ username }}</span>
        <button @click="handleLogout" class="logout-btn">登出</button>
      </div>
    </div>
    
    <!-- Content Wrapper -->
    <div class="content-wrapper">
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
    </div>
    
    <!-- Main Chat Area -->
    <div class="main-content">
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
          <div v-if="msg.qvl_downloads && msg.qvl_downloads.length > 0" class="qvl-downloads">
            <div class="downloads-label">📁 QVL 資料下載:</div>
            <div class="downloads-list">
              <button v-for="(download, downloadIdx) in msg.qvl_downloads" 
                      :key="downloadIdx" 
                      @click="downloadQVL(download.collection_name)"
                      class="download-btn">
                📥 {{ download.collection_name }}.txt
              </button>
            </div>
          </div>
          <div v-if="msg.retrieved_docs && msg.retrieved_docs.length > 0" class="retrieved-docs">
            <div class="docs-label">📚 檢索到的相關文檔:</div>
            <div class="docs-list">
              <div v-for="(doc, docIdx) in msg.retrieved_docs" 
                   :key="docIdx" 
                   class="doc-item">
                <div class="doc-score">相關度: {{ (doc.score * 100).toFixed(1) }}%</div>
                <div class="doc-text">{{ doc.text.substring(0, 200) }}{{ doc.text.length > 200 ? '...' : '' }}</div>
                <div v-if="doc.metadata" class="doc-metadata">
                  來源: {{ doc.metadata.filename || '未知' }}
                </div>
              </div>
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
          
          <!-- RAG 標籤 -->
          <div v-if="useRAG" class="rag-tag">
            <span class="tag-icon">📚</span>
            <span class="tag-text">RAG 對話</span>
            <!-- 取消 RAG 按鈕 -->
            <button 
              type="button" 
              @click="cancelRAG" 
              class="tag-cancel-btn"
              title="Cancel RAG chat"
            >
              ×
            </button>
          </div>
          
          <input 
            v-model="input" 
            type="text" 
            :placeholder="getInputPlaceholder()"
            :disabled="loading"
            :class="{ 'web-search-mode': useWebSearch, 'rag-mode': useRAG }"
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
            <div class="dropdown-item" @click="toggleRAGChat">
              <span class="dropdown-icon">📚</span>
              <span class="dropdown-text">RAG 對話</span>
              <span v-if="useRAG" class="dropdown-check">✓</span>
            </div>
          </div>
        </div>
        
        <!-- Spec Search 勾選框 -->
        <div class="spec-search-checkbox">
          <label>
            <input type="checkbox" v-model="useSpecSearch" @change="toggleSpecSearch" :disabled="loading" />
            <span class="checkbox-text">Spec Search</span>
          </label>
        </div>
        
        <button type="submit" :disabled="loading || !input.trim()">
          {{ getSendButtonText() }}
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
    </div> <!-- Close content-wrapper -->
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { sendChat, sendWebSearchChat, sendSpecSearchChat, sendRAGChat, getChatHistory, getAllSessions, deleteSession, downloadQVLFile } from '../api/chat'
import { logout, getStoredUsername } from '../api/auth'
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
const useSpecSearch = ref(false)
const useRAG = ref(false)

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
    
    // 確保 DOM 更新後再滾動到底部
    await nextTick()
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
  // 立即更新顯示列表包含新會話（添加到頂部）
  if (!sessions.value.includes(newSessionId)) {
    sessions.value.unshift(newSessionId)
    updateDisplaySessions()
  }
}

// 切換 web search 模式
const toggleWebSearch = () => {
  useWebSearch.value = !useWebSearch.value
  
  // 如果啟用 Web Search，則禁用其他模式（互斥邏輯）
  if (useWebSearch.value) {
    useSpecSearch.value = false
    useRAG.value = false
  }
  
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

// 切換 spec search 模式
const toggleSpecSearch = () => {
  // v-model 已經自動更新了 useSpecSearch.value
  // 只需要處理互斥邏輯
  if (useSpecSearch.value) {
    useWebSearch.value = false
    useRAG.value = false
  }
}

// 切換 RAG 模式
const toggleRAGChat = () => {
  useRAG.value = !useRAG.value
  
  // 如果啟用 RAG，則禁用其他模式（互斥邏輯）
  if (useRAG.value) {
    useWebSearch.value = false
    useSpecSearch.value = false
  }
  
  showWebSearchMenu.value = false // 選擇後關閉選單
}

// 取消 RAG 模式
const cancelRAG = () => {
  useRAG.value = false
  showWebSearchMenu.value = false
}

// 取得輸入框 placeholder
const getInputPlaceholder = () => {
  if (useRAG.value) return '基於您的知識庫進行智能問答...'
  if (useWebSearch.value) return 'Search the web and chat...'
  return 'Type your message...'
}

// 取得發送按鈕文字
const getSendButtonText = () => {
  if (loading.value) {
    if (useRAG.value) return 'RAG 處理中'
    if (useWebSearch.value) return 'Searching'
    if (useSpecSearch.value) return 'Spec Searching'
    return 'Sending'
  }
  return 'Send'
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
      
      // 將新會話加入列表頂部
      sessions.value.unshift(sessionId)
      updateDisplaySessions()
    }
    
    // 根據模式選擇不同的API調用
    let response
    if (useRAG.value) {
      response = await sendRAGChat(userInput, sessionId)
    } else if (useSpecSearch.value) {
      response = await sendSpecSearchChat(userInput, sessionId)
    } else if (useWebSearch.value) {
      response = await sendWebSearchChat(userInput, sessionId)
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
    
    // 如果有 QVL 下載連結，添加到消息中
    if (response.qvl_downloads && response.qvl_downloads.length > 0) {
      botMsg.qvl_downloads = response.qvl_downloads
    }
    
    // 如果有RAG檢索的文檔，添加到消息中
    if (response.retrieved_docs && response.retrieved_docs.length > 0) {
      botMsg.retrieved_docs = response.retrieved_docs
    }
    
    messages.value.push(botMsg)
    
    // 確保會話在列表中（處理後端可能改變 session ID 的情況）
    if (response.session_id && response.session_id !== sessionId) {
      currentSession.value = response.session_id
      if (!sessions.value.includes(response.session_id)) {
        sessions.value.unshift(response.session_id)
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
    // 添加小延遲確保渲染完成
    setTimeout(() => {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }, 10)
  }
}

// 格式化時間戳
const formatTimestamp = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString()
}

// 切換會話
const switchSession = async (sessionId) => {
  if (currentSession.value !== sessionId) {
    currentSession.value = sessionId
    await loadChatHistory()
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

// QVL 檔案下載處理
const downloadQVL = async (collectionName) => {
  try {
    console.log(`Downloading QVL file: ${collectionName}`)
    
    // 調用 API 下載檔案
    const blob = await downloadQVLFile(collectionName)
    
    // 創建下載連結
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${collectionName}.txt`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    
    console.log(`QVL file ${collectionName}.txt downloaded successfully`)
  } catch (error) {
    console.error('Failed to download QVL file:', error)
    alert(`下載 QVL 檔案失敗: ${error.message}`)
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
/* Navigation Bar */
.nav-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: white;
  border-bottom: 1px solid #e0e0e0;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  z-index: 10;
}

.nav-tabs {
  display: flex;
  gap: 0.5rem;
}

.nav-tab {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  text-decoration: none;
  color: #666;
  border-radius: 8px;
  transition: all 0.3s ease;
  font-weight: 500;
}

.nav-tab:hover, .nav-tab.active {
  background: #007bff;
  color: white;
}

.nav-icon {
  font-size: 1.2rem;
}

.user-info-nav {
  display: flex;
  align-items: center;
  gap: 1rem;
  color: #666;
  font-weight: 500;
}

.logout-btn {
  padding: 0.5rem 1rem;
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
  font-weight: 500;
}

.logout-btn:hover {
  background: #c82333;
}

/* Content Wrapper */
.content-wrapper {
  display: flex;
  flex: 1;
  height: calc(100vh - 80px); /* Account for nav-bar height */
  overflow: hidden;
}

/* App Layout Update */
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}


/* Update existing sidebar to work with content-wrapper */
.sidebar {
  width: 300px;
  background: white;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* Update main-content to work with content-wrapper */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f8f9fa;
}

/* Ensure proper height for chat messages */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* Chat input stays at bottom */
.chat-input {
  padding: 1rem;
  background: white;
  border-top: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .nav-bar {
    padding: 0.75rem 1rem;
  }
  
  .nav-tabs {
    gap: 0.25rem;
  }
  
  .nav-tab {
    padding: 0.5rem 1rem;
    font-size: 0.9rem;
  }
  
  .content-wrapper {
    flex-direction: column;
  }
  
  .sidebar {
    width: 100%;
    height: 200px;
    border-right: none;
    border-bottom: 1px solid #e0e0e0;
  }
  
  .retrieved-docs {
    padding: 0.75rem;
  }
  
  .doc-item {
    padding: 0.75rem;
  }
}
</style> 