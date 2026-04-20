import axios, { type AxiosError, type AxiosResponse } from 'axios'
import { getApiErrorMessage } from './errors'
import type { ApiEnvelope } from './types'

const baseURL = import.meta.env.VITE_API_BASE ?? '/api'

const client = axios.create({
  baseURL,
  timeout: 120000,
})

function isSuccessEnvelope(payload: unknown): payload is ApiEnvelope {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'success' in payload &&
    (payload as ApiEnvelope).success === true &&
    'data' in payload
  )
}

client.interceptors.response.use(
  (res: AxiosResponse) => {
    const payload = res.data
    if (isSuccessEnvelope(payload)) {
      return { ...res, data: payload.data }
    }
    return res
  },
  (err: AxiosError) => {
    const msg = getApiErrorMessage(err)
    console.error('[API Error]', msg, err.response?.status)
    return Promise.reject(err)
  }
)

export default client
export { baseURL }
