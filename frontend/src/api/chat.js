import axios from 'axios'

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
  const res = await axios.post('/chat', payload)
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
  const res = await axios.get('/chat/history', { params })
  return res.data.history
}

/**
 * Get all available session IDs.
 * @returns {Promise<Array>} - Array of session IDs.
 */
export async function getAllSessions() {
  const res = await axios.get('/chat/sessions')
  return res.data.sessions
}

/**
 * Health check endpoint.
 * @returns {Promise<Object>} - Health status.
 */
export async function healthCheck() {
  const res = await axios.get('/health')
  return res.data
} 