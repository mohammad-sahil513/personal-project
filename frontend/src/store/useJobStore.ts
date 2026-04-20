import { create } from 'zustand'
import type { WorkflowStatusData } from '../api/types'

export type DocType = 'PDD' | 'SDD' | 'UAT'

/** UI-facing template row (mapped from API). */
export interface Template {
  id: string
  template_id: string
  filename: string
  type: string
  template_type: string | null
  status: string
  description: string
  sections_preview: string[]
  is_custom?: boolean
}

export interface Section {
  section_id: string
  title: string
}

export interface DocumentOutput {
  type: DocType
  sections: Section[]
}

type UiStatus = 'idle' | 'running' | 'completed' | 'failed'

interface JobStore {
  documentId: string | null
  uploadedFile: File | null
  selectedDocs: DocType[]
  /** One template per deliverable type (required for each selected DocType). */
  selectedTemplateByType: Partial<Record<DocType, string>>

  workflowRunByType: Partial<Record<DocType, string>>
  workflowDetailByType: Partial<Record<DocType, WorkflowStatusData>>

  status: UiStatus
  progress: number
  currentStep: string
  errorMessage: string | null
  perTypeProgress: Partial<Record<DocType, number>>
  perTypeStep: Partial<Record<DocType, string>>

  documents: DocumentOutput[]
  activDoc: DocType | null
  activeSectionId: string | null
  sectionContent: string | null

  setDocumentId: (id: string | null) => void
  setUploadedFile: (f: File | null) => void
  toggleDoc: (doc: DocType) => void
  setSelectedDocs: (docs: DocType[]) => void
  setSelectedTemplateForType: (doc: DocType, templateId: string | null) => void
  setWorkflowRun: (doc: DocType, workflowRunId: string) => void
  setWorkflowRuns: (runs: Partial<Record<DocType, string>>) => void
  setWorkflowDetail: (doc: DocType, detail: WorkflowStatusData) => void
  setStatus: (s: UiStatus) => void
  setProgress: (p: number, step?: string) => void
  setPerTypeProgress: (doc: DocType, p: number, step?: string) => void
  setDocuments: (docs: DocumentOutput[]) => void
  setActiveDoc: (doc: DocType) => void
  setActiveSectionId: (id: string | null) => void
  setSectionContent: (c: string | null) => void
  setError: (msg: string | null) => void
  reset: () => void
}

const initialState = {
  documentId: null,
  uploadedFile: null,
  selectedDocs: ['PDD', 'SDD', 'UAT'] as DocType[],
  selectedTemplateByType: {} as Partial<Record<DocType, string>>,
  workflowRunByType: {} as Partial<Record<DocType, string>>,
  workflowDetailByType: {} as Partial<Record<DocType, WorkflowStatusData>>,
  status: 'idle' as const,
  progress: 0,
  currentStep: '',
  errorMessage: null,
  perTypeProgress: {} as Partial<Record<DocType, number>>,
  perTypeStep: {} as Partial<Record<DocType, string>>,
  documents: [] as DocumentOutput[],
  activDoc: null,
  activeSectionId: null,
  sectionContent: null,
}

export const useJobStore = create<JobStore>((set) => ({
  ...initialState,

  setDocumentId: (id) => set({ documentId: id }),
  setUploadedFile: (f) => set({ uploadedFile: f }),
  toggleDoc: (doc) =>
    set((state) => {
      const next = state.selectedDocs.includes(doc)
        ? state.selectedDocs.filter((d) => d !== doc)
        : [...state.selectedDocs, doc]
      const tpl = { ...state.selectedTemplateByType }
      if (!next.includes(doc)) delete tpl[doc]
      return { selectedDocs: next, selectedTemplateByType: tpl }
    }),
  setSelectedDocs: (docs) => set({ selectedDocs: docs }),
  setSelectedTemplateForType: (doc, templateId) =>
    set((state) => {
      const next = { ...state.selectedTemplateByType }
      if (templateId) next[doc] = templateId
      else delete next[doc]
      return { selectedTemplateByType: next }
    }),
  setWorkflowRun: (doc, workflowRunId) =>
    set((state) => ({
      workflowRunByType: { ...state.workflowRunByType, [doc]: workflowRunId },
    })),
  setWorkflowRuns: (runs) =>
    set({ workflowRunByType: runs, workflowDetailByType: {}, documents: [] }),
  setWorkflowDetail: (doc, detail) =>
    set((state) => ({
      workflowDetailByType: { ...state.workflowDetailByType, [doc]: detail },
    })),
  setStatus: (s) => set({ status: s }),
  setProgress: (p, step) => set({ progress: p, currentStep: step ?? '' }),
  setPerTypeProgress: (doc, p, step) =>
    set((state) => ({
      perTypeProgress: { ...state.perTypeProgress, [doc]: p },
      ...(step !== undefined ? { perTypeStep: { ...state.perTypeStep, [doc]: step } } : {}),
    })),
  setDocuments: (docs) => set({ documents: docs }),
  setActiveDoc: (doc) => set({ activDoc: doc, activeSectionId: null, sectionContent: null }),
  setActiveSectionId: (id) => set({ activeSectionId: id }),
  setSectionContent: (c) => set({ sectionContent: c }),
  setError: (msg) => set({ errorMessage: msg }),
  reset: () => set(initialState),
}))
