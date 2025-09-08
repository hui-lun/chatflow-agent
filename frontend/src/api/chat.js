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

/**
 * Send a chat message to the backend /chat API.
 * @param {string} message - The user's message.
 * @param {string} sessionId - Optional session ID for conversation grouping.
 * @returns {Promise<Object>} - The response from the backend.
 */
export async function sendChat(message, sessionId = null) {
  const payload = { message }
  if (sessionId) {
    payload.session_id = sessionId
  }
  const res = await api.post('/chat', payload)
  return res.data
}

/**
 * Get chat history from the backend.
 * @param {string} sessionId - Optional session ID to filter history.
 * @param {number} limit - Maximum number of messages to retrieve.
 * @returns {Promise<Array>} - Array of chat history items.
 */
export async function getChatHistory(sessionId = null, limit = 50) {
  const params = { limit }
  if (sessionId) {
    params.session_id = sessionId
  }
  const res = await api.get('/chat/history', { params })
  return res.data.history
}

/**
 * Get all available session IDs.
 * @returns {Promise<Array>} - Array of session IDs.
 */
export async function getAllSessions() {
  const res = await api.get('/chat/sessions')
  return res.data.sessions
}

/**
 * Delete a specific session and all its chat messages.
 * @param {string} sessionId - The session ID to delete.
 * @returns {Promise<Object>} - The response from the backend.
 */
export async function deleteSession(sessionId) {
  const res = await api.delete(`/chat/sessions/${sessionId}`)
  return res.data
}

/**
 * Send a chat message with web search functionality to the backend.
 * @param {string} message - The user's message.
 * @param {string} sessionId - Optional session ID for conversation grouping.
 * @returns {Promise<Object>} - The response from the backend with search sources.
 */
export async function sendWebSearchChat(message, sessionId = null) {
  const payload = { message }
  if (sessionId) {
    payload.session_id = sessionId
  }
  const res = await api.post('/chat/web-search', payload)
  return res.data
}

/**
 * Send a chat message with spec search functionality to the backend.
 * @param {string} message - The user's message.
 * @param {string} sessionId - Optional session ID for conversation grouping.
 * @returns {Promise<Object>} - The response from the backend.
 */
export async function sendSpecSearchChat(message, sessionId = null) {
  const payload = { message }
  if (sessionId) {
    payload.session_id = sessionId
  }
  const res = await api.post('/chat/spec-search', payload)
  return res.data
}

/**
 * Download QVL file from the backend.
 * @param {string} collectionName - The QVL collection name.
 * @returns {Promise<Blob>} - The file blob for download.
 */
export async function downloadQVLFile(collectionName) {
  const res = await api.get(`/download/qvl/${collectionName}`, {
    responseType: 'blob'
  })
  return res.data
}

/**
 * Health check endpoint.
 * @returns {Promise<Object>} - Health status.
 */
export async function healthCheck() {
  const res = await api.get('/health')
  return res.data
}

/**
 * Upload a PDF file to the knowledge base.
 * @param {File} file - The PDF file to upload.
 * @returns {Promise<Object>} - The upload response from the backend.
 */
export async function uploadFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  
  const res = await api.post('/kb/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
  return res.data
}

/**
 * Get the list of uploaded files in the knowledge base.
 * @returns {Promise<Object>} - The files list response from the backend.
 */
export async function getFiles() {
  const res = await api.get('/kb/files')
  return res.data
}

/**
 * Delete a file from the knowledge base.
 * @param {string} fileId - The ID of the file to delete.
 * @returns {Promise<Object>} - The deletion response from the backend.
 */
export async function deleteFile(fileId) {
  const res = await api.delete(`/kb/files/${fileId}`)
  return res.data
}

/**
 * Send a RAG chat message to the backend.
 * @param {string} message - The user's message.
 * @param {string} sessionId - Optional session ID for conversation grouping.
 * @returns {Promise<Object>} - The response from the backend with retrieved documents.
 */
export async function sendRAGChat(message, sessionId = null) {
  const payload = { message }
  if (sessionId) {
    payload.session_id = sessionId
  }
  const res = await api.post('/chat/rag', payload)
  return res.data
}

/**
 * Send a chat message with streaming response.
 * @param {string} message - The user's message.
 * @param {string} sessionId - Optional session ID for conversation grouping.
 * @param {Function} onToken - Callback function to handle each token received.
 * @param {Function} onComplete - Callback function when streaming is complete.
 * @param {Function} onError - Callback function for handling errors.
 * @returns {Promise<void>}
 */
export async function sendChatStreaming(message, sessionId = null, onToken, onComplete, onError) {
  try {
    const token = localStorage.getItem('token')
    const payload = { message }
    if (sessionId) {
      payload.session_id = sessionId
    }

    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      if (response.status === 401) {
        // Token 無效，清除本地儲存並重新導向登入頁面
        localStorage.removeItem('token')
        localStorage.removeItem('username')
        window.location.href = '/login'
        return
      }
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    try {
      while (true) {
        const { done, value } = await reader.read()
        
        if (done) {
          onComplete()
          break
        }

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')
        
        for (const line of lines) {
          if (line.trim()) {
            try {
              const data = JSON.parse(line)
              if (data.token) {
                onToken(data.token)
              } else if (data.error) {
                onError(new Error(data.error))
                return
              }
            } catch (parseError) {
              console.warn('Failed to parse streaming data:', line, parseError)
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  } catch (error) {
    onError(error)
  }
}

/**
 * Send a web search chat message with streaming response.
 * @param {string} message - The user's message.
 * @param {string} sessionId - Optional session ID for conversation grouping.
 * @param {Function} onToken - Callback function to handle each token received.
 * @param {Function} onComplete - Callback function when streaming is complete.
 * @param {Function} onError - Callback function for handling errors.
 * @param {Function} onSearchSources - Callback function to handle search sources.
 * @returns {Promise<void>}
 */
export async function sendWebSearchChatStreaming(message, sessionId = null, onToken, onComplete, onError, onSearchSources) {
  try {
    const token = localStorage.getItem('token')
    const payload = { message }
    if (sessionId) {
      payload.session_id = sessionId
    }

    const response = await fetch(`${API_BASE_URL}/chat/web-search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('username')
        window.location.href = '/login'
        return
      }
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    try {
      while (true) {
        const { done, value } = await reader.read()
        
        if (done) {
          onComplete()
          break
        }

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')
        
        for (const line of lines) {
          if (line.trim()) {
            try {
              const data = JSON.parse(line)
              if (data.token) {
                onToken(data.token)
              } else if (data.search_sources) {
                onSearchSources(data.search_sources)
              } else if (data.error) {
                onError(new Error(data.error))
                return
              }
            } catch (parseError) {
              console.warn('Failed to parse streaming data:', line, parseError)
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  } catch (error) {
    onError(error)
  }
}

/**
 * Send a spec search chat message with streaming response.
 * @param {string} message - The user's message.
 * @param {string} sessionId - Optional session ID for conversation grouping.
 * @param {Function} onToken - Callback function to handle each token received.
 * @param {Function} onComplete - Callback function when streaming is complete.
 * @param {Function} onError - Callback function for handling errors.
 * @param {Function} onQVLDownloads - Callback function to handle QVL downloads.
 * @returns {Promise<void>}
 */
export async function sendSpecSearchChatStreaming(message, sessionId = null, onToken, onComplete, onError, onQVLDownloads) {
  try {
    const token = localStorage.getItem('token')
    const payload = { message }
    if (sessionId) {
      payload.session_id = sessionId
    }

    const response = await fetch(`${API_BASE_URL}/chat/spec-search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('username')
        window.location.href = '/login'
        return
      }
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    try {
      while (true) {
        const { done, value } = await reader.read()
        
        if (done) {
          onComplete()
          break
        }

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')
        
        for (const line of lines) {
          if (line.trim()) {
            try {
              const data = JSON.parse(line)
              if (data.token) {
                onToken(data.token)
              } else if (data.qvl_downloads) {
                onQVLDownloads(data.qvl_downloads)
              } else if (data.error) {
                onError(new Error(data.error))
                return
              }
            } catch (parseError) {
              console.warn('Failed to parse streaming data:', line, parseError)
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  } catch (error) {
    onError(error)
  }
}

/**
 * Send a RAG chat message with streaming response.
 * @param {string} message - The user's message.
 * @param {string} sessionId - Optional session ID for conversation grouping.
 * @param {Function} onToken - Callback function to handle each token received.
 * @param {Function} onComplete - Callback function when streaming is complete.
 * @param {Function} onError - Callback function for handling errors.
 * @param {Function} onRetrievedDocs - Callback function to handle retrieved documents.
 * @returns {Promise<void>}
 */
export async function sendRAGChatStreaming(message, sessionId = null, onToken, onComplete, onError, onRetrievedDocs) {
  try {
    const token = localStorage.getItem('token')
    const payload = { message }
    if (sessionId) {
      payload.session_id = sessionId
    }

    const response = await fetch(`${API_BASE_URL}/chat/rag`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('username')
        window.location.href = '/login'
        return
      }
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    try {
      while (true) {
        const { done, value } = await reader.read()
        
        if (done) {
          onComplete()
          break
        }

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')
        
        for (const line of lines) {
          if (line.trim()) {
            try {
              const data = JSON.parse(line)
              if (data.token) {
                onToken(data.token)
              } else if (data.retrieved_docs) {
                onRetrievedDocs(data.retrieved_docs)
              } else if (data.error) {
                onError(new Error(data.error))
                return
              }
            } catch (parseError) {
              console.warn('Failed to parse streaming data:', line, parseError)
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  } catch (error) {
    onError(error)
  }
} 