import client from './client'
import type { DocumentUploadData } from './types'

export async function uploadDocument(file: File): Promise<DocumentUploadData> {
  const form = new FormData()
  form.append('file', file)
  const res = await client.post<DocumentUploadData>('/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}
