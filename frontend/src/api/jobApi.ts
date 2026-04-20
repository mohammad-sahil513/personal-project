import client from './client'
import { DocType } from '../store/useJobStore'

export interface CreateJobPayload {
  documents: DocType[]
  template_id: string
}

export interface JobProgress {
  progress_percent: number
  current_step: string
  status: 'created' | 'uploaded' | 'running' | 'completed' | 'failed'
}

export const jobApi = {
  createJob: async (payload: CreateJobPayload) => {
    const res = await client.post<{ job_id: string; status: string }>('/jobs', payload)
    return res.data
  },

  uploadFile: async (jobId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    const res = await client.post(`/jobs/${jobId}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },

  startJob: async (jobId: string) => {
    const res = await client.post(`/jobs/${jobId}/start`)
    return res.data
  },

  getProgress: async (jobId: string): Promise<JobProgress> => {
    const res = await client.get<JobProgress>(`/jobs/${jobId}/progress`)
    return res.data
  },
}
