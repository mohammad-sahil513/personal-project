import { useRef, useState, DragEvent, ChangeEvent } from 'react'
import { Upload, X, FileText, Plus, Check } from 'lucide-react'
import { templateApi } from '../../api/templateApi'

const DOC_TYPES = ['PDD', 'SDD', 'UAT'] as const
type DocType = typeof DOC_TYPES[number]

interface Props {
  onSuccess: () => void
}

export function AddTemplatePanel({ onSuccess }: Props) {
  const [selectedType, setSelectedType] = useState<DocType | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [description, setDescription] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    const ext = f.name.split('.').pop()?.toLowerCase()
    if (ext !== 'docx') {
      setError('Only DOCX files are accepted for templates.')
      return
    }
    setError(null)
    setFile(f)
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  const canSubmit = selectedType && file && !uploading

  const handleSubmit = async () => {
    if (!canSubmit) {
      if (!selectedType) setError('Select a document type first.')
      else if (!file) setError('Upload a DOCX template file.')
      return
    }
    setError(null)
    setUploading(true)
    try {
      await templateApi.uploadTemplate({
        file,
        doc_type: selectedType,
        description,
      })
      setSuccess(true)
      setTimeout(() => {
        setSuccess(false)
        setFile(null)
        setSelectedType(null)
        setDescription('')
        onSuccess()
      }, 1500)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Upload failed. Check backend logs.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="border border-[#E5E5E5] bg-white">
      {/* Panel header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-[#E5E5E5] bg-[#FAFAFA]">
        <div className="w-6 h-6 bg-black flex items-center justify-center shrink-0">
          <Plus size={13} color="#FFD400" />
        </div>
        <h3 className="font-display font-bold text-lg uppercase tracking-wide text-black">
          Add New Template
        </h3>
      </div>

      <div className="p-6 space-y-6">
        {/* Step 1: Document type */}
        <div>
          <label className="font-body text-[10px] tracking-widest uppercase text-[#6B6B6B] font-medium block mb-3">
            Document Type
          </label>
          <div className="flex gap-3">
            {DOC_TYPES.map((type) => {
              const active = selectedType === type
              return (
                <button
                  key={type}
                  onClick={() => setSelectedType(type)}
                  className={`flex-1 py-3 border-2 font-display font-bold text-xl uppercase tracking-widest transition-all ${
                    active
                      ? 'border-black bg-black text-[#FFD400]'
                      : 'border-[#E5E5E5] bg-white text-black hover:border-black'
                  }`}
                >
                  {type}
                </button>
              )
            })}
          </div>
        </div>

        {/* Step 2: Description */}
        <div>
          <label className="font-body text-[10px] tracking-widest uppercase text-[#6B6B6B] font-medium block mb-2">
            Description <span className="text-[#C0C0C0] normal-case tracking-normal">(optional)</span>
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Custom SDD for financial systems"
            className="w-full border border-[#E5E5E5] px-4 py-2.5 font-body text-sm text-black placeholder:text-[#C0C0C0] focus:outline-none focus:border-black transition-colors"
          />
        </div>

        {/* Step 3: File drop */}
        <div>
          <label className="font-body text-[10px] tracking-widest uppercase text-[#6B6B6B] font-medium block mb-2">
            Template File (DOCX)
          </label>

          {file ? (
            <div className="border border-[#E5E5E5] px-4 py-3 flex items-center gap-3 animate-fade-in">
              <FileText size={18} color="#6B6B6B" />
              <span className="font-body text-sm text-black flex-1 truncate">{file.name}</span>
              <span className="font-body text-xs text-[#999]">
                {(file.size / 1024).toFixed(0)} KB
              </span>
              <button onClick={() => setFile(null)} className="shrink-0 hover:bg-[#F0F0F0] p-1 transition-colors">
                <X size={14} color="#999" />
              </button>
            </div>
          ) : (
            <div
              onDrop={onDrop}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
              onDragLeave={() => setIsDragging(false)}
              onClick={() => fileRef.current?.click()}
              className={`border-2 border-dashed cursor-pointer p-8 flex flex-col items-center gap-3 transition-all ${
                isDragging
                  ? 'border-[#FFD400] bg-yellow-50'
                  : 'border-[#D0D0D0] bg-[#FAFAFA] hover:border-black hover:bg-white'
              }`}
            >
              <Upload size={20} color={isDragging ? '#000' : '#999'} />
              <p className="font-body text-sm text-[#6B6B6B] text-center">
                Drop DOCX here or{' '}
                <span className="text-black font-medium underline">browse</span>
              </p>
            </div>
          )}
          <input
            ref={fileRef}
            type="file"
            accept=".docx"
            className="hidden"
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              const f = e.target.files?.[0]
              if (f) handleFile(f)
              e.target.value = ''
            }}
          />
        </div>

        {/* Error */}
        {error && (
          <p className="font-body text-xs text-red-500 animate-fade-in">{error}</p>
        )}

        {/* Readiness + Submit */}
        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-4">
            <Dot active={!!selectedType} label="Type" />
            <Dot active={!!file} label="File" />
          </div>

          <button
            onClick={handleSubmit}
            disabled={!canSubmit || success}
            className={`flex items-center gap-2 px-6 py-3 font-display font-bold text-sm uppercase tracking-widest transition-all ${
              success
                ? 'bg-[#FFD400] text-black'
                : canSubmit
                ? 'bg-black text-[#FFD400] hover:bg-[#1A1A1A]'
                : 'bg-[#F0F0F0] text-[#C0C0C0] cursor-not-allowed'
            }`}
          >
            {success ? (
              <>
                <Check size={14} strokeWidth={3} />
                Uploaded
              </>
            ) : uploading ? (
              'Uploading…'
            ) : (
              'Upload Template'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

function Dot({ active, label }: { active: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-1.5 h-1.5 rounded-full transition-colors ${active ? 'bg-black' : 'bg-[#D0D0D0]'}`} />
      <span className={`font-body text-xs transition-colors ${active ? 'text-black font-medium' : 'text-[#C0C0C0]'}`}>
        {label}
      </span>
    </div>
  )
}
