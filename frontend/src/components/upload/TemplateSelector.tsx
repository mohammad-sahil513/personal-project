import { useEffect, useState, useRef } from 'react'
import { ChevronRight, Upload, Check } from 'lucide-react'
import { templateApi } from '../../api/templateApi'
import { useJobStore, Template } from '../../store/useJobStore'

export function TemplateSelector() {
  const { selectedTemplateId, setSelectedTemplateId } = useJobStore()
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const fetchTemplates = async () => {
    try {
      setLoading(true)
      const data = await templateApi.listTemplates()
      setTemplates(data)
      // Auto-select first if none selected
      if (!selectedTemplateId && data.length > 0) {
        setSelectedTemplateId(data[0].id)
      }
    } catch {
      setError('Could not load templates. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchTemplates() }, [])

  const handleUploadTemplate = async (file: File) => {
    try {
      setUploading(true)
      await templateApi.uploadTemplate({ file, doc_type: "custom" })
      await fetchTemplates()
    } catch {
      alert('Failed to upload template.')
    } finally {
      setUploading(false)
    }
  }

  if (loading) {
    return (
      <div className="grid grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="border border-[#E5E5E5] p-5 animate-pulse">
            <div className="h-4 bg-[#E5E5E5] w-16 mb-3" />
            <div className="h-3 bg-[#E5E5E5] w-full mb-2" />
            <div className="h-3 bg-[#E5E5E5] w-3/4" />
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="border border-[#E5E5E5] p-6 text-center">
        <p className="font-body text-sm text-[#6B6B6B]">{error}</p>
        <button onClick={fetchTemplates} className="mt-3 font-body text-xs underline text-black">
          Retry
        </button>
      </div>
    )
  }

  return (
    <div>
      <div className="grid grid-cols-3 gap-4">
        {templates.map((tpl) => {
          const selected = selectedTemplateId === tpl.id
          return (
            <button
              key={tpl.id}
              onClick={() => setSelectedTemplateId(tpl.id)}
              className={`p-5 border-2 text-left transition-all relative group ${
                selected
                  ? 'border-black bg-black text-white'
                  : 'border-[#E5E5E5] bg-white hover:border-black'
              }`}
            >
              {/* Selected badge */}
              {selected && (
                <div className="absolute top-3 right-3 w-5 h-5 bg-[#FFD400] flex items-center justify-center">
                  <Check size={11} color="#000" strokeWidth={3} />
                </div>
              )}

              {/* Template type badge */}
              <div className={`inline-block px-2 py-0.5 mb-3 text-[10px] font-body font-semibold tracking-widest uppercase ${
                tpl.is_custom
                  ? selected ? 'bg-[#FFD400] text-black' : 'bg-black text-[#FFD400]'
                  : selected ? 'bg-white/20 text-white' : 'bg-[#F7F7F7] text-[#6B6B6B]'
              }`}>
                {tpl.is_custom ? 'Custom' : 'Standard'}
              </div>

              <p className={`font-display font-bold text-xl tracking-wide uppercase mb-2 ${
                selected ? 'text-[#FFD400]' : 'text-black'
              }`}>
                {tpl.type || tpl.id}
              </p>

              <p className={`font-body text-xs mb-4 ${selected ? 'text-white/60' : 'text-[#6B6B6B]'}`}>
                {tpl.description}
              </p>

              {/* Section preview */}
              {tpl.sections_preview?.length > 0 && (
                <div className="space-y-1">
                  {tpl.sections_preview.slice(0, 4).map((s, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <ChevronRight size={10} color={selected ? '#FFD400' : '#999'} />
                      <span className={`font-body text-xs truncate ${selected ? 'text-white/70' : 'text-[#6B6B6B]'}`}>
                        {s}
                      </span>
                    </div>
                  ))}
                  {tpl.sections_preview.length > 4 && (
                    <p className={`font-body text-xs pl-4 ${selected ? 'text-white/40' : 'text-[#C0C0C0]'}`}>
                      +{tpl.sections_preview.length - 4} more
                    </p>
                  )}
                </div>
              )}
            </button>
          )
        })}

        {/* Upload custom template card */}
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="border-2 border-dashed border-[#D0D0D0] p-5 text-left hover:border-black transition-all flex flex-col items-center justify-center gap-3 min-h-[160px]"
        >
          <div className="w-10 h-10 bg-[#F7F7F7] flex items-center justify-center">
            <Upload size={18} color="#6B6B6B" />
          </div>
          <p className="font-body text-sm font-medium text-black text-center">
            {uploading ? 'Uploading…' : 'Upload Custom Template'}
          </p>
          <p className="font-body text-xs text-[#6B6B6B] text-center">DOCX format</p>
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".docx"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) handleUploadTemplate(f)
          }}
        />
      </div>
    </div>
  )
}
