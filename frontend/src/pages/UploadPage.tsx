import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, AlertCircle } from 'lucide-react'
import { FileUploader } from '../components/upload/FileUploader'
import { DocumentSelector } from '../components/upload/DocumentSelector'
import { TemplateSelector } from '../components/upload/TemplateSelector'
import { useJobStore } from '../store/useJobStore'
import { jobApi } from '../api/jobApi'

export function UploadPage() {
  const navigate = useNavigate()
  const {
    uploadedFile,
    selectedDocs,
    selectedTemplateId,
    setJobId,
    setStatus,
    setError,
  } = useJobStore()

  const [submitting, setSubmitting] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)

  const canSubmit = uploadedFile && selectedDocs.length > 0 && selectedTemplateId

  const handleGenerate = async () => {
    if (!canSubmit) {
      if (!uploadedFile) setValidationError('Please upload a BRD or DOCX file.')
      else if (selectedDocs.length === 0) setValidationError('Select at least one document type.')
      else if (!selectedTemplateId) setValidationError('Select a template to use.')
      return
    }
    setValidationError(null)

    try {
      setSubmitting(true)

      // 1. Create job
      const { job_id } = await jobApi.createJob({
        documents: selectedDocs,
        template_id: selectedTemplateId,
      })
      setJobId(job_id)
      setStatus('created')

      // 2. Upload file
      await jobApi.uploadFile(job_id, uploadedFile)
      setStatus('uploaded')

      // 3. Start job
      await jobApi.startJob(job_id)
      setStatus('running')

      navigate('/progress')
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Failed to start pipeline. Check your backend.'
      setError(msg)
      setValidationError(msg)
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-56px)] bg-white">
      {/* Hero strip */}
      <div className="bg-black text-white px-8 py-12">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-start gap-4 mb-6">
            <div className="w-1 h-12 bg-[#FFD400]" />
            <div>
              <p className="font-body text-xs tracking-widest uppercase text-[#FFD400] mb-1 font-medium">
                AI SDLC Platform
              </p>
              <h1 className="font-display font-bold text-5xl uppercase leading-none tracking-tight text-white">
                Document<br />Generator
              </h1>
            </div>
          </div>
          <p className="font-body text-sm text-white/50 max-w-lg leading-relaxed">
            Upload your Business Requirements Document and let the pipeline generate
            enterprise-grade PDD, SDD, and UAT documentation automatically.
          </p>
        </div>
      </div>

      {/* Form sections */}
      <div className="max-w-5xl mx-auto px-8 py-12">
        <div className="space-y-12">

          {/* Step 1 — Upload */}
          <section className="animate-slide-up">
            <SectionLabel number="01" label="Upload Document" />
            <FileUploader />
          </section>

          {/* Step 2 — Select documents */}
          <section className="animate-slide-up" style={{ animationDelay: '0.1s' }}>
            <SectionLabel number="02" label="Output Documents" />
            <DocumentSelector />
          </section>

          {/* Step 3 — Template */}
          <section className="animate-slide-up" style={{ animationDelay: '0.15s' }}>
            <SectionLabel number="03" label="Select Template" />
            <TemplateSelector />
          </section>

          {/* Validation error */}
          {validationError && (
            <div className="flex items-center gap-3 border border-red-200 bg-red-50 px-5 py-4 animate-fade-in">
              <AlertCircle size={16} color="#DC2626" />
              <p className="font-body text-sm text-red-600">{validationError}</p>
            </div>
          )}

          {/* Generate button */}
          <div className="pt-2 animate-slide-up" style={{ animationDelay: '0.2s' }}>
            <button
              onClick={handleGenerate}
              disabled={submitting}
              className={`group flex items-center gap-4 px-10 py-5 font-display font-bold text-xl uppercase tracking-widest transition-all ${
                submitting
                  ? 'bg-[#E5E5E5] text-[#999] cursor-not-allowed'
                  : canSubmit
                  ? 'bg-black text-[#FFD400] hover:bg-[#FFD400] hover:text-black'
                  : 'bg-[#F7F7F7] text-[#C0C0C0] hover:bg-[#E5E5E5]'
              }`}
            >
              {submitting ? 'Starting Pipeline…' : 'Generate Documents'}
              {!submitting && (
                <ArrowRight
                  size={20}
                  className="transition-transform group-hover:translate-x-1"
                />
              )}
            </button>

            {/* Readiness summary */}
            <div className="flex items-center gap-6 mt-5">
              <StatusDot active={!!uploadedFile} label="File ready" />
              <StatusDot active={selectedDocs.length > 0} label={`${selectedDocs.length} doc(s) selected`} />
              <StatusDot active={!!selectedTemplateId} label="Template selected" />
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}

function SectionLabel({ number, label }: { number: string; label: string }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <span className="font-display font-bold text-3xl text-[#FFD400] leading-none">{number}</span>
      <div className="h-px flex-1 bg-[#E5E5E5]" />
      <span className="font-body text-xs font-semibold tracking-widest uppercase text-[#6B6B6B]">{label}</span>
    </div>
  )
}

function StatusDot({ active, label }: { active: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className={`w-2 h-2 rounded-full transition-colors ${active ? 'bg-black' : 'bg-[#D0D0D0]'}`} />
      <span className={`font-body text-xs transition-colors ${active ? 'text-black font-medium' : 'text-[#C0C0C0]'}`}>
        {label}
      </span>
    </div>
  )
}
