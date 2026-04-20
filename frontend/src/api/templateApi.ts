import client from './client'
import { Template } from '../store/useJobStore'

export interface TemplateUploadPayload {
  file: File
  doc_type: string
  description?: string
}

export interface TemplatePreview {
  id: string
  type: string
  description: string
  sections_preview: string[]
  content?: string
  section_details?: Array<{ title: string; description: string }>
}

export const templateApi = {
  listTemplates: async (): Promise<Template[]> => {
    const res = await client.get<Template[]>('/templates')
    return res.data
  },

  getTemplatePreview: async (templateId: string): Promise<TemplatePreview> => {
    try {
      const res = await client.get<TemplatePreview>(`/templates/${templateId}/preview`)
      return res.data
    } catch {
      const res = await client.get<TemplatePreview>(`/templates/${templateId}`)
      return res.data
    }
  },

  uploadTemplate: async (payload: TemplateUploadPayload) => {
    const form = new FormData()
    form.append('file', payload.file)
    form.append('doc_type', payload.doc_type)
    if (payload.description) form.append('description', payload.description)
    const res = await client.post('/templates/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },

  deleteTemplate: async (templateId: string) => {
    const res = await client.delete(`/templates/${templateId}`)
    return res.data
  },
}
