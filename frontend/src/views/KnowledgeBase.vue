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
    await deleteFile(fileId)
    console.log('檔案刪除成功')
    
    // 從列表中移除
    files.value = files.value.filter(f => f.file_id !== fileId)
    
    showDeleteConfirm.value = false
    fileToDelete.value = null
    
  } catch (error) {
    console.error('刪除檔案失敗:', error)
    alert('刪除檔案失敗: ' + error.message)
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

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}

/* Navigation Bar */
.nav-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: white;
  border-bottom: 1px solid #e0e0e0;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
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
}

.nav-tab:hover, .nav-tab.active {
  background: #007bff;
  color: white;
}

.nav-icon {
  font-size: 1.2rem;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 1rem;
  color: #666;
}

.logout-btn {
  padding: 0.5rem 1rem;
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
}

.logout-btn:hover {
  background: #c82333;
}

/* Knowledge Base Content */
.kb-content {
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
}

.kb-header {
  text-align: center;
  margin-bottom: 2rem;
}

.kb-header h2 {
  color: #333;
  margin-bottom: 0.5rem;
}

.kb-description {
  color: #666;
  max-width: 600px;
  margin: 0 auto;
  line-height: 1.5;
}

/* Upload Area */
.upload-area {
  border: 2px dashed #ddd;
  border-radius: 12px;
  padding: 3rem 2rem;
  text-align: center;
  transition: all 0.3s ease;
  background: white;
  margin-bottom: 2rem;
}

.upload-area.drag-over {
  border-color: #007bff;
  background: #f8f9fa;
}

.upload-content .upload-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.upload-content h3 {
  color: #333;
  margin-bottom: 0.5rem;
}

.upload-content p {
  color: #666;
  margin-bottom: 1.5rem;
}

.upload-btn {
  padding: 0.75rem 2rem;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 1rem;
  transition: background-color 0.3s;
}

.upload-btn:hover {
  background: #0056b3;
}

/* Upload Progress */
.upload-progress .progress-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.upload-progress h3 {
  color: #333;
  margin-bottom: 0.5rem;
}

.upload-progress p {
  color: #666;
  margin-bottom: 1rem;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: #e9ecef;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #007bff;
  transition: width 0.3s ease;
}

/* Files Section */
.files-section {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.files-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #e0e0e0;
}

.files-header h3 {
  color: #333;
  margin: 0;
}

.refresh-btn {
  padding: 0.5rem 1rem;
  background: #28a745;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
}

.refresh-btn:hover {
  background: #218838;
}

.refresh-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
}

/* Loading and Empty States */
.loading-state, .empty-state {
  text-align: center;
  padding: 3rem 1rem;
  color: #666;
}

.loading-spinner, .empty-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

/* Files List */
.files-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.file-item {
  display: flex;
  align-items: center;
  padding: 1rem;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.file-item:hover {
  border-color: #007bff;
  background: #f8f9fa;
}

.file-item.processing {
  opacity: 0.7;
}

.file-icon {
  font-size: 2rem;
  margin-right: 1rem;
}

.file-info {
  flex: 1;
}

.file-name {
  font-weight: 600;
  color: #333;
  margin-bottom: 0.25rem;
}

.file-meta {
  display: flex;
  gap: 1rem;
  color: #666;
  font-size: 0.9rem;
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.8rem;
  font-weight: 500;
}

.status-badge.processed {
  background: #d4edda;
  color: #155724;
}

.status-badge.processing {
  background: #fff3cd;
  color: #856404;
}

.status-badge.error {
  background: #f8d7da;
  color: #721c24;
}

.delete-btn {
  padding: 0.5rem;
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
  margin-left: 1rem;
}

.delete-btn:hover {
  background: #c82333;
}

.delete-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  padding: 2rem;
  max-width: 400px;
  width: 90%;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.modal-content h4 {
  color: #333;
  margin-bottom: 1rem;
}

.modal-content p {
  color: #666;
  margin-bottom: 2rem;
  line-height: 1.5;
}

.modal-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
}

.cancel-btn, .confirm-btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s;
}

.cancel-btn {
  background: #6c757d;
  color: white;
}

.cancel-btn:hover {
  background: #545b62;
}

.confirm-btn {
  background: #dc3545;
  color: white;
}

.confirm-btn:hover {
  background: #c82333;
}
</style>