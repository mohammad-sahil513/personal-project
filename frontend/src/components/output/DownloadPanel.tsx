import { Download, Package } from 'lucide-react'
import { useJobStore, DocType } from '../../store/useJobStore'
import { outputApi } from '../../api/outputApi'

export function DownloadPanel() {
  const { jobId, documents } = useJobStore()

  if (!jobId) return null

  return (
    <div className="border-t border-[#E5E5E5] bg-white px-6 py-4 flex items-center gap-4 flex-wrap">
      <span className="font-body text-xs font-medium tracking-widest uppercase text-[#999]">
        Download
      </span>

      {/* Download All ZIP */}
      <button
        onClick={() => outputApi.downloadAll(jobId)}
        className="flex items-center gap-2 bg-black text-white px-4 py-2 hover:bg-[#1A1A1A] transition-colors"
      >
        <Package size={14} color="#FFD400" />
        <span className="font-body text-xs font-medium">All Documents (ZIP)</span>
      </button>

      {/* Individual downloads */}
      {documents.map(({ type }) => (
        <button
          key={type}
          onClick={() => outputApi.downloadDoc(jobId, type as DocType)}
          className="flex items-center gap-2 border border-[#E5E5E5] bg-white text-black px-4 py-2 hover:border-black transition-colors"
        >
          <Download size={13} color="#6B6B6B" />
          <span className="font-body text-xs font-medium">{type}</span>
        </button>
      ))}
    </div>
  )
}
