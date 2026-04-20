import { useState } from 'react'
import { Eye, Trash2, ChevronRight, AlertCircle } from 'lucide-react'
import { Template } from '../../store/useJobStore'
import { templateApi } from '../../api/templateApi'
import { TemplatePreviewModal } from './TemplatePreviewModal'

interface Props {
  template: Template
  onDeleted: () => void
}

export function TemplateCard({ template, onDeleted }: Props) {
  const [showPreview, setShowPreview] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await templateApi.deleteTemplate(template.id)
      onDeleted()
    } catch {
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  return (
    <>
      <div className="border border-[#E5E5E5] bg-white hover:border-black transition-all group animate-fade-in">
        {/* Card top strip */}
        <div className="h-1 bg-[#FFD400]" />

        <div className="p-5">
          {/* Header row */}
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className={`font-body text-[9px] font-semibold tracking-widest uppercase px-2 py-0.5 ${
                  template.is_custom
                    ? 'bg-black text-[#FFD400]'
                    : 'bg-[#F0F0F0] text-[#6B6B6B]'
                }`}>
                  {template.is_custom ? 'Custom' : 'Standard'}
                </span>
              </div>
              <h4 className="font-display font-bold text-xl uppercase tracking-wide text-black leading-tight truncate">
                {template.id}
              </h4>
            </div>
          </div>

          {/* Description */}
          {template.description && (
            <p className="font-body text-xs text-[#6B6B6B] mb-4 leading-relaxed line-clamp-2">
              {template.description}
            </p>
          )}

          {/* Section preview list */}
          {template.sections_preview?.length > 0 && (
            <div className="space-y-1.5 mb-5">
              {template.sections_preview.slice(0, 4).map((s, i) => (
                <div key={i} className="flex items-center gap-2">
                  <ChevronRight size={10} color="#C0C0C0" className="shrink-0" />
                  <span className="font-body text-xs text-[#6B6B6B] truncate">{s}</span>
                </div>
              ))}
              {template.sections_preview.length > 4 && (
                <p className="font-body text-[10px] text-[#C0C0C0] pl-4">
                  +{template.sections_preview.length - 4} more sections
                </p>
              )}
            </div>
          )}

          {/* Actions */}
          {confirmDelete ? (
            <div className="border border-red-200 bg-red-50 p-3 animate-fade-in">
              <div className="flex items-center gap-2 mb-3">
                <AlertCircle size={13} color="#DC2626" />
                <p className="font-body text-xs text-red-600 font-medium">Delete this template?</p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex-1 py-1.5 bg-red-600 text-white font-body text-xs font-medium hover:bg-red-700 transition-colors"
                >
                  {deleting ? 'Deleting…' : 'Yes, Delete'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="flex-1 py-1.5 border border-[#E5E5E5] text-black font-body text-xs hover:border-black transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <button
                onClick={() => setShowPreview(true)}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-black text-white font-body text-xs font-medium hover:bg-[#1A1A1A] transition-colors group"
              >
                <Eye size={13} className="group-hover:scale-110 transition-transform" />
                Preview
              </button>
              {template.is_custom && (
                <button
                  onClick={() => setConfirmDelete(true)}
                  className="w-10 flex items-center justify-center border border-[#E5E5E5] text-[#999] hover:border-red-300 hover:text-red-500 transition-colors"
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {showPreview && (
        <TemplatePreviewModal
          template={template}
          onClose={() => setShowPreview(false)}
        />
      )}
    </>
  )
}
