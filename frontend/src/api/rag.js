import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'
const api = axios.create({ baseURL: API_BASE_URL })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/**
 * 上傳並索引 PDF 文件
 * @param {Object} params - 參數對象
 * @param {string} params.collection - 集合名稱
 * @param {string} params.userId - 用戶 ID
 * @param {File[]} params.files - 要上傳的文件數組
 * @param {number} [params.chunkSize] - 可選，分塊大小
 * @param {number} [params.chunkOverlap] - 可選，分塊重疊大小
 * @param {boolean} [params.autoChunk] - 是否啟用自動分塊
 * @returns {Promise<Object>} 索引結果
 */
export async function ragIndex({ 
  collection, 
  userId, 
  files, 
  chunkSize, 
  chunkOverlap, 
  autoChunk = false 
}) {
  const form = new FormData()
  form.append('collection', collection)
  form.append('user_id', userId)
  
  // 只有在明確提供時才添加這些參數
  if (chunkSize !== undefined) form.append('chunk_size', String(chunkSize))
  if (chunkOverlap !== undefined) form.append('chunk_overlap', String(chunkOverlap))
  form.append('auto_chunk', String(autoChunk))
  
  // 添加所有文件
  for (const f of files) {
    form.append('files', f)
  }
  
  try {
    const res = await api.post('/rag/index', form, { 
      headers: { 
        'Content-Type': 'multipart/form-data',
        'Accept': 'application/json'
      },
      // 增加超時時間，大文件上傳需要更長時間
      timeout: 600000 // 10分鐘
    })
    
    return res.data
  } catch (error) {
    console.error('RAG 索引錯誤:', error)
    
    // 提供更有用的錯誤信息
    let errorMessage = '索引文件時出錯'
    if (error.response) {
      // 服務器返回了錯誤狀態碼
      const { status, data } = error.response
      errorMessage = `[${status}] ${data?.detail || data?.message || '未知錯誤'}`
    } else if (error.request) {
      // 請求已發送但無響應
      errorMessage = '服務器無響應，請檢查網絡連接或稍後重試'
    } else if (error.code === 'ECONNABORTED') {
      errorMessage = '請求超時，請稍後重試或檢查網絡連接'
    }
    
    throw new Error(errorMessage)
  }
}

export async function ragQuery({ message, collection, userId, limit = 3 }) {
  const res = await api.post('/rag/query', { message, collection, user_id: userId, limit })
  return res.data
}


