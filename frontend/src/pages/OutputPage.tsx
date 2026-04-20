import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { DocumentTabs } from '../components/output/DocumentTabs'
import { SectionSidebar } from '../components/output/SectionSidebar'
import { DocxViewer } from '../components/output/DocxViewer'
import { DownloadPanel } from '../components/output/DownloadPanel'
import { useJobStore, DocType } from '../store/useJobStore'
import { outputApi } from '../api/outputApi'

export function OutputPage() {
  const navigate = useNavigate()
  const { jobId, status, documents, activDoc, setDocuments, setActiveDoc } = useJobStore()

  // Guard — redirect if no job
  useEffect(() => {
    if (!jobId) {
      navigate('/')
      return
    }

    // If documents haven't been loaded yet (e.g., navigated directly)
    if (documents.length === 0 && status === 'completed') {
      outputApi.getDocuments(jobId)
        .then((data) => {
          setDocuments(data.documents)
          if (data.documents.length > 0 && !activDoc) {
            setActiveDoc(data.documents[0].type as DocType)
          }
        })
        .catch(() => {})
    }

    // If we do have docs but no active tab, set first
    if (documents.length > 0 && !activDoc) {
      setActiveDoc(documents[0].type as DocType)
    }
  }, [jobId])

  return (
    <div className="h-[calc(100vh-56px)] flex flex-col bg-white">
      {/* Top bar */}
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

      {/* Document tabs */}
      {documents.length > 0 && (
        <div className="px-8 bg-white shrink-0">
          <DocumentTabs />
        </div>
      )}

      {/* Body: sidebar + viewer */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <div className="w-56 shrink-0 border-r border-[#E5E5E5] overflow-y-auto bg-white">
          <SectionSidebar />
        </div>

        {/* Document viewer */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <DocxViewer />
        </div>
      </div>

      {/* Download bar */}
      <DownloadPanel />
    </div>
  )
}
