import { useRef, useState, DragEvent, ChangeEvent } from 'react'
import { Upload, File, X } from 'lucide-react'
import { useJobStore } from '../../store/useJobStore'

export function FileUploader() {
  const { uploadedFile, setUploadedFile } = useJobStore()
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (ext === 'pdf' || ext === 'docx') {
      setUploadedFile(file)
    } else {
      alert('Only PDF and DOCX files are supported.')
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const onDragOver = (e: DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const onDragLeave = () => setIsDragging(false)

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  if (uploadedFile) {
    return (
      <div className="border border-[#E5E5E5] bg-white p-4 flex items-center gap-4 animate-fade-in">
        <div className="w-10 h-10 bg-black flex items-center justify-center shrink-0">
          <File size={18} color="#FFD400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-body font-medium text-sm text-black truncate">{uploadedFile.name}</p>
          <p className="font-body text-xs text-[#6B6B6B] mt-0.5">{formatSize(uploadedFile.size)}</p>
        </div>
        <button
          onClick={() => setUploadedFile(null)}
          className="w-8 h-8 flex items-center justify-center hover:bg-[#F7F7F7] transition-colors shrink-0"
        >
          <X size={16} color="#6B6B6B" />
        </button>
      </div>
    )
  }

  return (
    <div
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onClick={() => inputRef.current?.click()}
      className={`border-2 border-dashed transition-all cursor-pointer p-10 flex flex-col items-center gap-4
        ${isDragging
          ? 'border-[#FFD400] bg-yellow-50'
          : 'border-[#D0D0D0] bg-[#F7F7F7] hover:border-black hover:bg-white'
        }`}
    >
      <div className={`w-12 h-12 flex items-center justify-center transition-colors ${isDragging ? 'bg-[#FFD400]' : 'bg-black'}`}>
        <Upload size={22} color={isDragging ? '#000' : '#FFD400'} />
      </div>
      <div className="text-center">
        <p className="font-display font-bold text-xl uppercase tracking-wide text-black">
          Drop your BRD here
        </p>
        <p className="font-body text-sm text-[#6B6B6B] mt-1">
          or <span className="text-black font-medium underline">browse files</span> — PDF or DOCX accepted
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx"
        onChange={onChange}
        className="hidden"
      />
    </div>
  )
}
