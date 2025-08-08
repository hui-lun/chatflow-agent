import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'
const api = axios.create({ baseURL: API_BASE_URL })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export async function ragIndex({ collection, userId, files, chunkSize = 1000, chunkOverlap = 200 }) {
  const form = new FormData()
  form.append('collection', collection)
  form.append('user_id', userId)
  form.append('chunk_size', String(chunkSize))
  form.append('chunk_overlap', String(chunkOverlap))
  for (const f of files) form.append('files', f)
  const res = await api.post('/rag/index', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  return res.data
}

export async function ragQuery({ message, collection, userId, limit = 3 }) {
  const res = await api.post('/rag/query', { message, collection, user_id: userId, limit })
  return res.data
}


