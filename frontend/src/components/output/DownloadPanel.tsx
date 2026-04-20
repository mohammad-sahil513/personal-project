import { Download } from 'lucide-react'
import { useJobStore, type DocType } from '../../store/useJobStore'
import { outputApi } from '../../api/outputApi'

export function DownloadPanel() {
  const { documents, workflowDetailByType } = useJobStore()

  const hasAnyOutput = documents.some(
    (d) => workflowDetailByType[d.type as DocType]?.output_id
  )

  if (!documents.length) return null

  return (
    <div className="border-t border-[#E5E5E5] bg-white px-6 py-4 flex items-center gap-4 flex-wrap">
      <span className="font-body text-xs font-medium tracking-widest uppercase text-[#999]">
        Download
      </span>

      {documents.map(({ type }) => {
        const oid = workflowDetailByType[type as DocType]?.output_id
        const ready =
          (workflowDetailByType[type as DocType]?.status || '').toUpperCase() === 'COMPLETED' &&
          Boolean(oid)
        return (
          <button
            key={type}
            type="button"
            disabled={!ready}
            onClick={() => oid && outputApi.downloadByOutputId(oid)}
            className={`flex items-center gap-2 border px-4 py-2 transition-colors ${
              ready
                ? 'border-[#E5E5E5] bg-white text-black hover:border-black'
                : 'border-[#F0F0F0] text-[#C0C0C0] cursor-not-allowed'
            }`}
          >
            <Download size={13} color={ready ? '#6B6B6B' : '#E5E5E5'} />
            <span className="font-body text-xs font-medium">{type} (DOCX)</span>
          </button>
        )
      })}

      {!hasAnyOutput && (
        <span className="font-body text-xs text-[#999]">
          Outputs appear when the workflow status is completed and an output_id is present.
        </span>
      )}
    </div>
  )
}
