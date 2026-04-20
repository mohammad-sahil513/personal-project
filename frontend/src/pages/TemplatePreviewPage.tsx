import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowLeft, AlertCircle, Loader2 } from 'lucide-react'
import { templateApi } from '../api/templateApi'
import type { TemplateDto } from '../api/types'
import { getApiErrorMessage } from '../api/errors'

function formatArtifactLine(a: unknown, i: number): string {
  if (a !== null && typeof a === 'object' && 'name' in a && typeof (a as { name: string }).name === 'string') {
    return `- ${(a as { name: string }).name}`
  }
  try {
    return `- \`${JSON.stringify(a)}\``
  } catch {
    return `- (artifact ${i + 1})`
  }
}

function buildMetadataMarkdown(dto: TemplateDto): string {
  const lines: string[] = []
  lines.push(`# ${dto.filename}`)
  lines.push('')
  lines.push('Metadata from the template registry (`GET /templates/{id}`). Section structure is determined when you run a workflow, not from this preview.')
  lines.push('')
  lines.push('## Details')
  lines.push('')
  lines.push('| Field | Value |')
  lines.push('| --- | --- |')
  lines.push(`| template_id | \`${dto.template_id}\` |`)
  lines.push(`| template_type | ${dto.template_type ?? '—'} |`)
  lines.push(`| version | ${dto.version ?? '—'} |`)
  lines.push(`| status | **${dto.status}** |`)
  lines.push(`| compile_job_id | ${dto.compile_job_id ?? '—'} |`)
  lines.push(`| created_at | ${dto.created_at} |`)
  lines.push(`| updated_at | ${dto.updated_at} |`)
  lines.push('')
  lines.push('## Compiled artifacts')
  lines.push('')
  const arts = dto.compiled_artifacts ?? []
  if (arts.length === 0) {
    lines.push('_None stored on this template record._')
  } else {
    lines.push(`_Count: ${arts.length}_`)
    lines.push('')
    arts.forEach((a, i) => lines.push(formatArtifactLine(a, i)))
  }
  return lines.join('\n')
}

export function TemplatePreviewPage() {
  const navigate = useNavigate()
  const { templateId } = useParams<{ templateId: string }>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dto, setDto] = useState<TemplateDto | null>(null)

  const fetchTemplate = useCallback(async () => {
    if (!templateId) {
      setError('Template ID is missing.')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await templateApi.getTemplateRaw(templateId)
      setDto(data)
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, 'Could not load template preview.'))
      setDto(null)
    } finally {
      setLoading(false)
    }
  }, [templateId])

  useEffect(() => {
    fetchTemplate()
  }, [fetchTemplate])

  return (
    <div className="min-h-[calc(100vh-56px)] bg-[#F0F0F0]">
      <div className="bg-black text-white px-8 py-8">
        <div className="max-w-5xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-4 min-w-0">
            <div className="w-1 h-10 bg-[#FFD400] shrink-0" />
            <div className="min-w-0">
              <p className="font-body text-xs tracking-widest uppercase text-[#FFD400] mb-1 font-medium">
                Template preview
              </p>
              <h1 className="font-display font-bold text-2xl uppercase tracking-tight truncate">
                {dto?.template_type ?? 'Template'} — {templateId}
              </h1>
            </div>
          </div>
          <button
            type="button"
            onClick={() => navigate('/templates')}
            className="flex items-center gap-2 px-4 py-2 border border-white/20 text-white/80 hover:text-white hover:border-white/40 transition-colors"
          >
            <ArrowLeft size={14} />
            Back to Library
          </button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-10">
        {loading ? (
          <div className="flex flex-col items-center justify-center min-h-[320px] gap-4">
            <Loader2 size={28} className="animate-spin text-[#999]" />
            <p className="font-body text-sm text-[#999]">Loading template…</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center min-h-[320px] gap-4 px-8 text-center">
            <AlertCircle size={28} color="#DC2626" />
            <p className="font-body text-sm text-red-600">{error}</p>
            <button type="button" onClick={fetchTemplate} className="font-body text-xs underline text-black">
              Retry
            </button>
          </div>
        ) : dto ? (
          <div className="bg-white w-full shadow-[0_1px_4px_rgba(0,0,0,0.08)] px-12 py-12">
            <div className="docx-prose">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{buildMetadataMarkdown(dto)}</ReactMarkdown>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
