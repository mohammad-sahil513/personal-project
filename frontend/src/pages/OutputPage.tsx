import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { DocumentTabs } from '../components/output/DocumentTabs'
import { SectionSidebar } from '../components/output/SectionSidebar'
import { DocxViewer } from '../components/output/DocxViewer'
import { DownloadPanel } from '../components/output/DownloadPanel'
import { useJobStore, type DocType } from '../store/useJobStore'
import { getWorkflow } from '../api/workflowApi'

export function OutputPage() {
  const navigate = useNavigate()
  const {
    selectedDocs,
    workflowRunByType,
    documents,
    setDocuments,
    setWorkflowDetail,
    setActiveDoc,
    setActiveSectionId,
    setSectionContent,
  } = useJobStore()

  useEffect(() => {
    const hasRuns = selectedDocs.some((d) => workflowRunByType[d])
    if (!hasRuns) {
      navigate('/')
      return
    }

    let cancelled = false
    ;(async () => {
      const docs: { type: DocType; sections: { section_id: string; title: string }[] }[] = []
      for (const doc of selectedDocs) {
        const runId = workflowRunByType[doc]
        if (!runId) continue
        const w = await getWorkflow(runId)
        if (cancelled) return
        setWorkflowDetail(doc, w)
        docs.push({
          type: doc,
          sections:
            w.assembled_document?.sections?.map((s) => ({
              section_id: s.section_id,
              title: s.title,
            })) ?? [],
        })
      }
      if (cancelled) return
      setDocuments(docs)
      if (docs.length > 0) {
        const firstType = docs[0].type
        setActiveDoc(firstType)
        const wf = useJobStore.getState().workflowDetailByType[firstType]
        const sec = wf?.assembled_document?.sections?.[0]
        if (sec) {
          setActiveSectionId(sec.section_id)
          setSectionContent(sec.content ?? '_No content for this section._')
        }
      }
    })().catch(() => {})

    return () => {
      cancelled = true
    }
  }, [
    navigate,
    selectedDocs,
    workflowRunByType,
    setDocuments,
    setWorkflowDetail,
    setActiveDoc,
    setActiveSectionId,
    setSectionContent,
  ])

  return (
    <div className="h-[calc(100vh-56px)] flex flex-col bg-white">
      <div className="flex items-center justify-between px-8 py-5 border-b border-[#E5E5E5] bg-white shrink-0">
        <div>
          <p className="font-body text-[10px] tracking-widest uppercase text-[#999] font-medium mb-1">
            Generated Output
          </p>
          <h1 className="font-display font-bold text-2xl uppercase text-black tracking-tight leading-none">
            Document Review
          </h1>
        </div>
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 border border-[#E5E5E5] px-4 py-2.5 hover:border-black transition-colors group"
        >
          <Plus size={14} className="group-hover:rotate-90 transition-transform" />
          <span className="font-body text-xs font-medium text-black">New Job</span>
        </button>
      </div>

      {documents.length > 0 && (
        <div className="px-8 bg-white shrink-0">
          <DocumentTabs />
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <div className="w-56 shrink-0 border-r border-[#E5E5E5] overflow-y-auto bg-white">
          <SectionSidebar />
        </div>

        <div className="flex-1 flex flex-col overflow-hidden">
          <DocxViewer />
        </div>
      </div>

      <DownloadPanel />
    </div>
  )
}
