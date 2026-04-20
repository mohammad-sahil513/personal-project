import { useEffect, useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { X, FileText, ChevronRight, Loader2, AlertCircle } from 'lucide-react'
import { templateApi, TemplatePreview } from '../../api/templateApi'
import { Template } from '../../store/useJobStore'

interface Props {
  template: Template
  onClose: () => void
}

const DOC_COLORS: Record<string, string> = {
  PDD: '#FFD400',
  SDD: '#FFD400',
  UAT: '#FFD400',
}

function buildFallbackMarkdown(preview: TemplatePreview): string {
  const lines: string[] = []
  lines.push(`# ${preview.type} Template — ${preview.id}`)
  lines.push('')
  lines.push(`> ${preview.description}`)
  lines.push('')
  lines.push('---')
  lines.push('')
  lines.push('## Document Sections')
  lines.push('')

  if (preview.section_details?.length) {
    preview.section_details.forEach((s, i) => {
      lines.push(`### ${String(i + 1).padStart(2, '0')}. ${s.title}`)
      lines.push('')
      lines.push(s.description)
      lines.push('')
    })
  } else if (preview.sections_preview?.length) {
    preview.sections_preview.forEach((s, i) => {
      lines.push(`### ${String(i + 1).padStart(2, '0')}. ${s}`)
      lines.push('')
      lines.push('_Section content will be generated based on the uploaded BRD._')
      lines.push('')
    })
  }

  return lines.join('\n')
}

export function TemplatePreviewModal({ template, onClose }: Props) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<TemplatePreview | null>(null)
  const [activeSectionIdx, setActiveSectionIdx] = useState(0)

  const fetchPreview = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await templateApi.getTemplatePreview(template.id)
      setPreview(data)
    } catch {
      // Graceful fallback: build preview from what we already have
      setPreview({
        id: template.id,
        type: template.type || template.id.toUpperCase(),
        description: template.description || '',
        sections_preview: template.sections_preview || [],
      })
    } finally {
      setLoading(false)
    }
  }, [template.id])

  useEffect(() => {
    fetchPreview()
    // Lock body scroll
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [fetchPreview])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const sections = preview?.sections_preview ?? []
  const markdownContent = preview?.content ?? (preview ? buildFallbackMarkdown(preview) : '')
  const pages = markdownContent.split('<!-- PAGE_BREAK -->')
  const accent = DOC_COLORS[preview?.type ?? ''] ?? '#FFD400'

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch"
      style={{ background: 'rgba(0,0,0,0.75)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Modal panel */}
      <div className="relative flex flex-col w-full max-w-6xl mx-auto my-6 bg-white shadow-2xl animate-slide-up">

        {/* ── Header ── */}
        <div className="bg-black flex items-center gap-4 px-8 py-5 shrink-0">
          <div className="w-2 h-10 shrink-0" style={{ background: accent }} />
          <div className="flex-1 min-w-0">
            <p className="font-body text-[10px] tracking-widest uppercase font-medium mb-0.5"
               style={{ color: accent }}>
              Template Preview
            </p>
            <h2 className="font-display font-bold text-2xl uppercase text-white tracking-tight leading-none truncate">
              {preview?.type ?? template.type ?? template.id} — {template.id}
            </h2>
          </div>

          {/* Template meta badges */}
          <div className="flex items-center gap-3 shrink-0">
            <span className={`font-body text-[10px] font-semibold tracking-widest uppercase px-3 py-1 ${
              template.is_custom ? 'bg-[#FFD400] text-black' : 'bg-white/10 text-white/70'
            }`}>
              {template.is_custom ? 'Custom' : 'Standard'}
            </span>
            {sections.length > 0 && (
              <span className="font-body text-[10px] text-white/50">
                {sections.length} section{sections.length !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          <button
            onClick={onClose}
            className="w-9 h-9 flex items-center justify-center text-white/50 hover:text-white hover:bg-white/10 transition-colors shrink-0 ml-2"
          >
            <X size={18} />
          </button>
        </div>

        {/* ── Body ── */}
        <div className="flex flex-1 overflow-hidden">

          {/* Left: section nav */}
          {sections.length > 0 && (
            <div className="w-52 shrink-0 border-r border-[#E5E5E5] flex flex-col overflow-y-auto bg-[#FAFAFA]">
              <div className="px-4 py-3 border-b border-[#E5E5E5]">
                <p className="font-body text-[10px] tracking-widest uppercase text-[#999] font-medium">
                  Sections
                </p>
              </div>
              {sections.map((s, i) => (
                <button
                  key={i}
                  onClick={() => setActiveSectionIdx(i)}
                  className={`w-full text-left px-4 py-3 flex items-center gap-3 border-b border-[#F0F0F0] transition-all group ${
                    activeSectionIdx === i
                      ? 'bg-black text-white'
                      : 'hover:bg-[#F0F0F0] text-[#1A1A1A]'
                  }`}
                >
                  <span className={`font-body text-[10px] font-medium w-5 shrink-0 ${
                    activeSectionIdx === i ? 'text-[#FFD400]' : 'text-[#C0C0C0]'
                  }`}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className={`font-body text-xs flex-1 leading-snug ${
                    activeSectionIdx === i ? 'text-white font-medium' : ''
                  }`}>
                    {s}
                  </span>
                  <ChevronRight size={11} className={`shrink-0 ${
                    activeSectionIdx === i ? 'text-[#FFD400]' : 'text-[#D0D0D0]'
                  }`} />
                </button>
              ))}
            </div>
          )}

          {/* Right: document canvas */}
          <div className="flex-1 overflow-y-auto bg-[#F0F0F0]">
            {loading ? (
              <div className="flex flex-col items-center justify-center h-full gap-4">
                <Loader2 size={28} className="animate-spin text-[#999]" />
                <p className="font-body text-sm text-[#999]">Loading template…</p>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center h-full gap-4 px-8 text-center">
                <AlertCircle size={28} color="#DC2626" />
                <p className="font-body text-sm text-red-500">{error}</p>
                <button onClick={fetchPreview} className="font-body text-xs underline text-black">
                  Retry
                </button>
              </div>
            ) : preview ? (
              <div className="py-10 px-6">
                {/* Description banner */}
                {preview.description && (
                  <div className="max-w-[820px] mx-auto mb-4">
                    <div className="border-l-4 px-5 py-3 bg-white text-sm font-body text-[#6B6B6B]"
                         style={{ borderColor: accent }}>
                      {preview.description}
                    </div>
                  </div>
                )}

                {/* Pages */}
                {pages.map((pageContent, i) => (
                  <div
                    key={i}
                    className="bg-white w-full max-w-[820px] mx-auto shadow-[0_1px_4px_rgba(0,0,0,0.08)] px-16 py-14 mb-8 animate-fade-in"
                  >
                    <div className="docx-prose">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {pageContent.trim()}
                      </ReactMarkdown>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <FileText size={28} color="#C0C0C0" />
                <p className="font-body text-sm text-[#999]">No preview available.</p>
              </div>
            )}
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="border-t border-[#E5E5E5] bg-white px-8 py-4 flex items-center justify-between shrink-0">
          <p className="font-body text-xs text-[#999]">
            Press <kbd className="font-mono bg-[#F0F0F0] px-1.5 py-0.5 text-[10px]">Esc</kbd> to close
          </p>
          <button
            onClick={onClose}
            className="font-body text-xs font-medium px-6 py-2.5 bg-black text-white hover:bg-[#1A1A1A] transition-colors"
          >
            Close Preview
          </button>
        </div>
      </div>
    </div>
  )
}
