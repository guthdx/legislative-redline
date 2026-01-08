import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8004'

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Document endpoints
export const documentApi = {
  upload: async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  },

  parse: async (documentId) => {
    const response = await api.post(`/documents/${documentId}/parse`)
    return response.data
  },

  getCitations: async (documentId) => {
    const response = await api.get(`/documents/${documentId}/citations`)
    return response.data
  },

  compare: async (documentId) => {
    const response = await api.post(`/documents/${documentId}/compare`)
    return response.data
  },

  getResult: async (documentId) => {
    const response = await api.get(`/documents/${documentId}/result`)
    return response.data
  },
}

// Citation endpoints
export const citationApi = {
  fetchStatute: async (citationId) => {
    const response = await api.post(`/citations/${citationId}/fetch-statute`)
    return response.data
  },
}

// Health check
export const healthApi = {
  check: async () => {
    const response = await api.get('/health')
    return response.data
  },
}

export default api
