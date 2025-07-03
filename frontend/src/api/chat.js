import axios from 'axios'

/**
 * Send a chat message to the backend /chat API.
 * @param {string} message - The user's message.
 * @returns {Promise<string>} - The response from the backend.
 */
export async function sendChat(message) {
  const res = await axios.post('/chat', { message })
  return res.data.response
} 