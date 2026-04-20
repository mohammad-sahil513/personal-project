import axios from 'axios'

const client = axios.create({
  baseURL: 'http://localhost:8001',
  timeout: 30000,
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    console.error('[API Error]', err.response?.data ?? err.message)
    return Promise.reject(err)
  }
)

export default client
