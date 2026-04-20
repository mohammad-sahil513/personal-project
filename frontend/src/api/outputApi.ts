import client from './client'
import { DocumentOutput, DocType } from '../store/useJobStore'

export interface SectionContent {
  content: string
  evidence?: {
    sources?: string[]
    graph?: string[]
    guidelines?: string[]
  }
}

export const outputApi = {
  getDocuments: async (jobId: string): Promise<{ documents: DocumentOutput[] }> => {
    const res = await client.get(`/jobs/${jobId}/documents`)
    return res.data
  },

  getSectionContent: async (
    jobId: string,
    docType: DocType,
    sectionId: string
  ): Promise<SectionContent> => {
    const res = await client.get<SectionContent>(
      `/jobs/${jobId}/documents/${docType}/sections/${sectionId}`
    )
    return res.data
  },

  downloadAll: (jobId: string) => {
    window.open(`http://localhost:8001/jobs/${jobId}/download/all`, '_blank')
  },

  downloadDoc: (jobId: string, docType: DocType) => {
    window.open(`http://localhost:8001/jobs/${jobId}/download/${docType.toLowerCase()}`, '_blank')
  },
}
