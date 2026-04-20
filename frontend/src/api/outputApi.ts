import { baseURL } from './client'

function downloadUrl(path: string): string {
  if (baseURL.startsWith('http')) {
    return `${baseURL.replace(/\/$/, '')}${path}`
  }
  return `${window.location.origin}${baseURL.replace(/\/$/, '')}${path}`
}

export const outputApi = {
  downloadByOutputId: (outputId: string) => {
    window.open(downloadUrl(`/outputs/${outputId}/download`), '_blank')
  },
}
