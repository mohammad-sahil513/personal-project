import client from './client'
import type { TemplateDto, TemplateListData } from './types'
import type { Template } from '../store/useJobStore'

function dtoToTemplate(d: TemplateDto): Template {
  const t = (d.template_type || '').toUpperCase()
  const isCustom =
    t === 'CUSTOM' ||
    d.status === 'UPLOADED' ||
    (d.template_type != null && !['PDD', 'SDD', 'UAT'].includes(t))
  return {
    id: d.template_id,
    template_id: d.template_id,
    filename: d.filename,
    type: d.template_type || d.template_id,
    template_type: d.template_type,
    status: d.status,
    description: d.filename,
    sections_preview: [],
    is_custom: isCustom,
  }
}

export interface TemplateUploadPayload {
  file: File
  template_type: string
  version?: string
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
    const res = await client.get<TemplateListData>('/templates')
    const data = res.data
    return (data.items ?? []).map(dtoToTemplate)
  },

  getTemplateRaw: async (templateId: string): Promise<TemplateDto> => {
    const res = await client.get<TemplateDto>(`/templates/${templateId}`)
    return res.data
  },

  getTemplateBinary: async (templateId: string): Promise<ArrayBuffer> => {
    const res = await client.get<ArrayBuffer>(`/templates/${templateId}/download`, {
      responseType: 'arraybuffer',
    })
    return res.data
  },

  getTemplatePreview: async (templateId: string): Promise<TemplatePreview> => {
    const raw = await templateApi.getTemplateRaw(templateId)
    return {
      id: raw.template_id,
      type: raw.template_type || raw.template_id,
      description: raw.filename,
      sections_preview: [],
    }
  },

  uploadTemplate: async (payload: TemplateUploadPayload) => {
    const form = new FormData()
    form.append('file', payload.file)
    form.append('template_type', payload.template_type)
    if (payload.version) form.append('version', payload.version)
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
