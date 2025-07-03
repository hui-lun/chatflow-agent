<template>
  <div class="chat-container">
    <div class="chat-messages">
      <div v-for="(msg, idx) in messages" :key="idx" :class="['chat-message', msg.role]">
        <span>{{ msg.role === 'user' ? 'You' : 'Bot' }}: </span>{{ msg.content }}
      </div>
    </div>
    <form class="chat-input" @submit.prevent="sendMessage">
      <input v-model="input" type="text" placeholder="Type your message..." />
      <button type="submit" :disabled="loading || !input">Send</button>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { sendChat } from './api/chat'
import './assets/styles/main.scss'

const input = ref('')
const messages = ref([])
const loading = ref(false)

const sendMessage = async () => {
  if (!input.value.trim()) return
  const userMsg = { role: 'user', content: input.value }
  messages.value.push(userMsg)
  loading.value = true
  try {
    const res = await sendChat(input.value)
    messages.value.push({ role: 'bot', content: res })
  } catch (e) {
    messages.value.push({ role: 'bot', content: 'Error: ' + e.message })
  } finally {
    loading.value = false
    input.value = ''
  }
}
</script> 