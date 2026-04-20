import client from './client'
import type { WorkflowCreateData, WorkflowStatusData } from './types'

export interface CreateWorkflowPayload {
  document_id: string
  template_id: string
  start_immediately?: boolean
}

export async function createWorkflow(
  payload: CreateWorkflowPayload
): Promise<WorkflowCreateData> {
  const res = await client.post<WorkflowCreateData>('/workflow-runs', {
    document_id: payload.document_id,
    template_id: payload.template_id,
    start_immediately: payload.start_immediately ?? true,
  })
  return res.data as WorkflowCreateData
}

export async function getWorkflowStatus(workflowRunId: string): Promise<WorkflowStatusData> {
  const res = await client.get<WorkflowStatusData>(`/workflow-runs/${workflowRunId}/status`)
  return res.data as WorkflowStatusData
}

export async function getWorkflow(workflowRunId: string): Promise<WorkflowStatusData> {
  const res = await client.get<WorkflowStatusData>(`/workflow-runs/${workflowRunId}`)
  return res.data as WorkflowStatusData
}
