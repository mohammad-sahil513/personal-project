import { create } from 'zustand'

export type DocType = 'PDD' | 'SDD' | 'UAT'

export interface Template {
  id: string
  type: string
  sections_preview: string[]
  description: string
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

interface JobStore {
  // Job
  jobId: string | null
  status: 'idle' | 'created' | 'uploaded' | 'running' | 'completed' | 'failed'
  progress: number
  currentStep: string
  errorMessage: string | null

  // Upload page state
  uploadedFile: File | null
  selectedDocs: DocType[]
  selectedTemplateId: string | null

  // Output
  documents: DocumentOutput[]
  activDoc: DocType | null
  activeSectionId: string | null
  sectionContent: string | null
  sectionLoading: boolean

  // Actions
  setJobId: (id: string) => void
  setStatus: (s: JobStore['status']) => void
  setProgress: (p: number, step?: string) => void
  setUploadedFile: (f: File | null) => void
  toggleDoc: (doc: DocType) => void
  setSelectedDocs: (docs: DocType[]) => void
  setSelectedTemplateId: (id: string | null) => void
  setDocuments: (docs: DocumentOutput[]) => void
  setActiveDoc: (doc: DocType) => void
  setActiveSectionId: (id: string | null) => void
  setSectionContent: (c: string | null) => void
  setSectionLoading: (b: boolean) => void
  setError: (msg: string | null) => void
  reset: () => void
}

const initialState = {
  jobId: null,
  status: 'idle' as const,
  progress: 0,
  currentStep: '',
  errorMessage: null,
  uploadedFile: null,
  selectedDocs: ['PDD', 'SDD', 'UAT'] as DocType[],
  selectedTemplateId: null,
  documents: [],
  activDoc: null,
  activeSectionId: null,
  sectionContent: null,
  sectionLoading: false,
}

export const useJobStore = create<JobStore>((set) => ({
  ...initialState,

  setJobId: (id) => set({ jobId: id }),
  setStatus: (s) => set({ status: s }),
  setProgress: (p, step) => set({ progress: p, currentStep: step ?? '' }),
  setUploadedFile: (f) => set({ uploadedFile: f }),
  toggleDoc: (doc) =>
    set((state) => ({
      selectedDocs: state.selectedDocs.includes(doc)
        ? state.selectedDocs.filter((d) => d !== doc)
        : [...state.selectedDocs, doc],
    })),
  setSelectedDocs: (docs) => set({ selectedDocs: docs }),
  setSelectedTemplateId: (id) => set({ selectedTemplateId: id }),
  setDocuments: (docs) => set({ documents: docs }),
  setActiveDoc: (doc) => set({ activDoc: doc, activeSectionId: null, sectionContent: null }),
  setActiveSectionId: (id) => set({ activeSectionId: id }),
  setSectionContent: (c) => set({ sectionContent: c }),
  setSectionLoading: (b) => set({ sectionLoading: b }),
  setError: (msg) => set({ errorMessage: msg }),
  reset: () => set(initialState),
}))
