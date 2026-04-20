import { useEffect, useState, useCallback, useRef } from 'react'
import { X, Loader2, AlertCircle, ChevronDown, ChevronRight, FileText } from 'lucide-react'
import { renderAsync } from 'docx-preview'
import { templateApi } from '../../api/templateApi'
import type { TemplateDto } from '../../api/types'
import { getApiErrorMessage } from '../../api/errors'
import { Template } from '../../store/useJobStore'

interface Props {
  template: Template
  onClose: () => void
}

export function TemplatePreviewModal({ template, onClose }: Props) {
  const [loadingMeta, setLoadingMeta] = useState(true)
  const [loadingDocx, setLoadingDocx] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dto, setDto] = useState<TemplateDto | null>(null)
  const [showMetadata, setShowMetadata] = useState(false)
  const docxContainerRef = useRef<HTMLDivElement | null>(null)

  const fetchPreview = useCallback(async () => {
    setLoadingMeta(true)
    setLoadingDocx(true)
    setError(null)
    try {
      const [data, binary] = await Promise.all([
        templateApi.getTemplateRaw(template.id),
        templateApi.getTemplateBinary(template.id),
      ])
      setDto(data)
      if (docxContainerRef.current) {
        docxContainerRef.current.innerHTML = ''
        await renderAsync(binary, docxContainerRef.current, undefined, {
          className: 'docx-preview-content',
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
        })
      }
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Could not load template preview.'))
      setDto(null)
    } finally {
      setLoadingMeta(false)
      setLoadingDocx(false)
    }
  }, [template.id])

  useEffect(() => {
    fetchPreview()
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [fetchPreview])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const accent = '#FFD400'
  const titleType = dto?.template_type || template.type || template.id

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch"
      style={{ background: 'rgba(0,0,0,0.75)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="relative flex flex-col w-full max-w-6xl mx-auto my-6 bg-white shadow-2xl animate-slide-up">
        <div className="bg-black flex items-center gap-4 px-8 py-5 shrink-0">
          <div className="w-2 h-10 shrink-0" style={{ background: accent }} />
          <div className="flex-1 min-w-0">
            <p
              className="font-body text-[10px] tracking-widest uppercase font-medium mb-0.5"
              style={{ color: accent }}
            >
              Template preview
            </p>
            <h2 className="font-display font-bold text-2xl uppercase text-white tracking-tight leading-none truncate">
              {titleType} — {template.id}
            </h2>
          </div>
          <span
            className={`font-body text-[10px] font-semibold tracking-widest uppercase px-3 py-1 shrink-0 ${
              template.is_custom ? 'bg-[#FFD400] text-black' : 'bg-white/10 text-white/70'
            }`}
          >
            {template.is_custom ? 'Custom' : 'Standard'}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="w-9 h-9 flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 transition-colors shrink-0 ml-2"
          >
            <X size={18} />
          </button>
        </div>

        <div className="border-b border-[#E5E5E5] bg-white px-8 py-3">
          <button
            type="button"
            onClick={() => setShowMetadata((v) => !v)}
            className="inline-flex items-center gap-2 font-body text-xs font-semibold tracking-widest uppercase text-[#6B6B6B] hover:text-black"
          >
            {showMetadata ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            Metadata
          </button>
          {showMetadata && dto && (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 font-body text-xs text-[#6B6B6B]">
              <p><span className="font-semibold text-black">ID:</span> {dto.template_id}</p>
              <p><span className="font-semibold text-black">Type:</span> {dto.template_type ?? '—'}</p>
              <p><span className="font-semibold text-black">Version:</span> {dto.version ?? '—'}</p>
              <p><span className="font-semibold text-black">Status:</span> {dto.status}</p>
              <p><span className="font-semibold text-black">Created:</span> {dto.created_at}</p>
              <p><span className="font-semibold text-black">Updated:</span> {dto.updated_at}</p>
              <p><span className="font-semibold text-black">Compile job:</span> {dto.compile_job_id ?? '—'}</p>
              <p><span className="font-semibold text-black">Artifacts:</span> {dto.compiled_artifacts?.length ?? 0}</p>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto bg-[#F0F0F0] min-h-[420px]">
          {loadingMeta || loadingDocx ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[320px] gap-4">
              <Loader2 size={28} className="animate-spin text-[#999]" />
              <p className="font-body text-sm text-[#999]">Loading template DOCX…</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center min-h-[320px] gap-4 px-8 text-center">
              <AlertCircle size={28} color="#DC2626" />
              <p className="font-body text-sm text-red-600">{error}</p>
              <button type="button" onClick={fetchPreview} className="font-body text-xs underline text-black">
                Retry
              </button>
            </div>
          ) : (
            <div className="py-10 px-6">
              <div className="bg-white w-full max-w-[980px] mx-auto shadow-[0_1px_4px_rgba(0,0,0,0.08)] px-8 py-8 animate-fade-in">
                <div className="flex items-center gap-2 mb-4 text-[#6B6B6B]">
                  <FileText size={14} />
                  <p className="font-body text-xs uppercase tracking-widest">Document view</p>
                </div>
                <div ref={docxContainerRef} className="docx-preview-host" />
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-[#E5E5E5] bg-white px-8 py-4 flex items-center justify-between shrink-0">
          <p className="font-body text-xs text-[#999]">
            Press{' '}
            <kbd className="font-mono bg-[#F0F0F0] px-1.5 py-0.5 text-[10px]">Esc</kbd> to close
          </p>
          <button
            type="button"
            onClick={onClose}
            className="font-body text-xs font-medium px-6 py-2.5 bg-black text-white hover:bg-[#1A1A1A] transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
