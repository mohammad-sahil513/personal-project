import { isAxiosError, type AxiosError } from 'axios'

type ErrorBody = {
  success?: boolean
  message?: string
  errors?: Array<{ code?: string; message?: string; details?: unknown }>
  detail?: unknown
}

function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'object' && item !== null && 'msg' in item) {
          return String((item as { msg: string }).msg)
        }
        return JSON.stringify(item)
      })
      .join('; ')
  }
  if (detail !== null && typeof detail === 'object') {
    return JSON.stringify(detail)
  }
  return String(detail)
}

function formatEnvelopeErrors(errors: ErrorBody['errors']): string {
  if (!errors?.length) return ''
  return errors
    .map((e) => {
      const parts = [e.code, e.message].filter(Boolean)
      return parts.join(': ')
    })
    .filter(Boolean)
    .join('; ')
}

/**
 * Human-readable message from API failures (FastAPI `detail`, backend `error_response`, or network).
 */
export function getApiErrorMessage(err: unknown, fallback = 'Request failed'): string {
  if (isAxiosError(err)) {
    const ax = err as AxiosError<ErrorBody>
    const data = ax.response?.data
    if (data && typeof data === 'object') {
      if (data.success === false && typeof data.message === 'string' && data.message) {
        const errPart = formatEnvelopeErrors(data.errors)
        return errPart ? `${data.message} (${errPart})` : data.message
      }
      if (data.detail !== undefined) {
        const d = formatDetail(data.detail)
        if (d) return d
      }
      const errPart = formatEnvelopeErrors(data.errors)
      if (errPart) return errPart
      if (typeof data.message === 'string' && data.message) {
        return data.message
      }
    }
    if (ax.message) return ax.message
  }
  if (err instanceof Error && err.message) return err.message
  return fallback
}
