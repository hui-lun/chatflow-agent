<template>
  <div class="app-layout">
    <!-- Navigation Bar -->
    <div class="nav-bar">
      <div class="nav-tabs">
        <router-link to="/chat" class="nav-tab">
          <span class="nav-icon">💬</span>
          對話
        </router-link>
        <router-link to="/kb" class="nav-tab active">
          <span class="nav-icon">📚</span>
          知識庫
        </router-link>
      </div>
      <div class="user-info">
        <span>{{ username }}</span>
        <button @click="handleLogout" class="logout-btn">登出</button>
      </div>
    </div>
    
    <!-- Main Content -->
    <div class="kb-content">
      <div class="kb-header">
        <h2>📚 您的知識庫</h2>
        <p class="kb-description">上傳PDF檔案來建立您的專屬知識庫，之後可以在對話中使用RAG功能進行智能問答。</p>
      </div>
      
      <!-- File Upload Area -->
      <div class="upload-area" :class="{ 'drag-over': dragOver }" 
           @drop="handleDrop" 
           @dragover="handleDragOver" 
           @dragenter="handleDragEnter" 
           @dragleave="handleDragLeave">
        <div class="upload-content" v-if="!uploading">
          <div class="upload-icon">📎</div>
          <h3>拖拽PDF檔案到此處或點擊上傳</h3>
          <p>支援PDF格式，檔案大小限制50MB</p>
          <input 
            type="file" 
            ref="fileInput" 
            @change="handleFileSelect" 
            accept=".pdf" 
            style="display: none;"
          />
          <button @click="$refs.fileInput.click()" class="upload-btn">
            選擇檔案
          </button>
        </div>
        
        <!-- Upload Progress -->
        <div class="upload-progress" v-if="uploading">
          <div class="progress-icon">⏳</div>
          <h3>正在處理檔案...</h3>
          <p>{{ uploadStatus }}</p>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
          </div>
        </div>
      </div>
      
      <!-- File List -->
      <div class="files-section">
        <div class="files-header">
          <h3>已上傳的檔案 ({{ files.length }})</h3>
          <button @click="loadFiles" class="refresh-btn" :disabled="loading">
            🔄 刷新
          </button>
        </div>
        
        <div v-if="loading" class="loading-state">
          <div class="loading-spinner">⏳</div>
          <p>載入檔案列表中...</p>
        </div>
        
        <div v-else-if="files.length === 0" class="empty-state">
          <div class="empty-icon">📄</div>
          <h4>尚未上傳任何檔案</h4>
          <p>上傳您的第一個PDF檔案開始建立知識庫</p>
        </div>
        
        <div v-else class="files-list">
          <div 
            v-for="file in files" 
            :key="file.file_id" 
            class="file-item"
            :class="{ 'processing': file.status !== 'processed' }"
          >
            <div class="file-icon">📄</div>
            <div class="file-info">
              <div class="file-name">{{ file.filename }}</div>
              <div class="file-meta">
                <span class="file-size">{{ formatFileSize(file.file_size) }}</span>
                <span class="file-date">{{ formatDate(file.uploaded_at) }}</span>
                <span v-if="file.chunks_count" class="chunks-count">
                  {{ file.chunks_count }} 個文本塊
                </span>
              </div>
            </div>
            <div class="file-status">
              <span 
                class="status-badge" 
                :class="file.status"
              >
                {{ getStatusText(file.status) }}
              </span>
            </div>
            <div class="file-actions">
              <button 
                @click="confirmDeleteFile(file)" 
                class="delete-btn"
                :disabled="deletingFiles.includes(file.file_id)"
                title="刪除檔案"
              >
                {{ deletingFiles.includes(file.file_id) ? '⏳' : '🗑️' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Delete Confirmation Modal -->
    <div v-if="showDeleteConfirm" class="modal-overlay" @click="cancelDeleteFile">
      <div class="modal-content" @click.stop>
        <h4>確認刪除</h4>
        <p>確定要刪除「{{ fileToDelete?.filename }}」嗎？此操作無法復原。</p>
        <div class="modal-actions">
          <button @click="cancelDeleteFile" class="cancel-btn">取消</button>
          <button @click="executeDeleteFile" class="confirm-btn">刪除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { uploadFile, getFiles, deleteFile } from '../api/chat'
import { logout, getStoredUsername } from '../api/auth'
import '../assets/styles/main.scss'

const username = ref('')
const files = ref([])
const loading = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadStatus = ref('')
const dragOver = ref(false)
const showDeleteConfirm = ref(false)
const fileToDelete = ref(null)
const deletingFiles = ref([])

// 載入檔案列表
const loadFiles = async () => {
  loading.value = true
  try {
    const fileList = await getFiles()
    files.value = fileList.files || []
  } catch (error) {
    console.error('載入檔案列表失敗:', error)
    alert('載入檔案列表失敗: ' + error.message)
  } finally {
    loading.value = false
  }
}

// 檔案上傳處理
const handleFileUpload = async (file) => {
  if (!file) return
  
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    alert('僅支援PDF檔案')
    return
  }
  
  if (file.size > 50 * 1024 * 1024) {
    alert('檔案大小不能超過50MB')
    return
  }
  
  uploading.value = true
  uploadProgress.value = 0
  uploadStatus.value = '準備上傳...'
  
  try {
    // 模擬上傳進度
    uploadStatus.value = '上傳中...'
    uploadProgress.value = 30
    
    await new Promise(resolve => setTimeout(resolve, 500))
    
    uploadStatus.value = '處理PDF檔案...'
    uploadProgress.value = 60
    
    const result = await uploadFile(file)
    
    uploadStatus.value = '向量化處理中...'
    uploadProgress.value = 90
    
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    uploadProgress.value = 100
    uploadStatus.value = '完成！'
    
    console.log('檔案上傳成功:', result)
    alert(`檔案上傳成功！${result.message}`)
    
    // 重新載入檔案列表
    await loadFiles()
    
  } catch (error) {
    console.error('檔案上傳失敗:', error)
    alert('檔案上傳失敗: ' + error.message)
  } finally {
    uploading.value = false
    uploadProgress.value = 0
    uploadStatus.value = ''
  }
}

// 拖拽處理
const handleDragOver = (e) => {
  e.preventDefault()
}

const handleDragEnter = (e) => {
  e.preventDefault()
  dragOver.value = true
}

const handleDragLeave = (e) => {
  e.preventDefault()
  if (e.target === e.currentTarget) {
    dragOver.value = false
  }
}

const handleDrop = (e) => {
  e.preventDefault()
  dragOver.value = false
  
  const droppedFiles = Array.from(e.dataTransfer.files)
  if (droppedFiles.length > 0) {
    handleFileUpload(droppedFiles[0])
  }
}

// 檔案選擇處理
const handleFileSelect = (e) => {
  const selectedFiles = Array.from(e.target.files)
  if (selectedFiles.length > 0) {
    handleFileUpload(selectedFiles[0])
  }
}

// 刪除檔案
const confirmDeleteFile = (file) => {
  fileToDelete.value = file
  showDeleteConfirm.value = true
}

const cancelDeleteFile = () => {
  showDeleteConfirm.value = false
  fileToDelete.value = null
}

const executeDeleteFile = async () => {
  if (!fileToDelete.value) return
  
  const fileId = fileToDelete.value.file_id
  deletingFiles.value.push(fileId)
  
  try {
    const result = await deleteFile(fileId)
    console.log('檔案刪除成功:', result)
    
    // 顯示成功訊息
    alert('檔案已完全刪除（包含向量資料）')
    
    // 從列表中移除
    files.value = files.value.filter(f => f.file_id !== fileId)
    
    showDeleteConfirm.value = false
    fileToDelete.value = null
    
  } catch (error) {
    console.error('刪除檔案失敗:', error)
    const errorMessage = error.response?.data?.detail || error.message || '未知錯誤'
    alert('刪除檔案失敗: ' + errorMessage)
  } finally {
    deletingFiles.value = deletingFiles.value.filter(id => id !== fileId)
  }
}

// 工具函數
const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const formatDate = (dateString) => {
  const date = new Date(dateString)
  return date.toLocaleDateString('zh-TW') + ' ' + date.toLocaleTimeString('zh-TW', { 
    hour: '2-digit', 
    minute: '2-digit' 
  })
}

const getStatusText = (status) => {
  const statusMap = {
    'processed': '已處理',
    'processing': '處理中',
    'error': '錯誤',
    'pending': '等待中'
  }
  return statusMap[status] || status
}

const handleLogout = () => {
  logout()
}

// 組件掛載時載入資料
onMounted(async () => {
  username.value = getStoredUsername() || 'User'
  await loadFiles()
})
</script>

