import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, AlertCircle } from 'lucide-react'
import { FileUploader } from '../components/upload/FileUploader'
import { DocumentSelector } from '../components/upload/DocumentSelector'
import { TemplateSelector } from '../components/upload/TemplateSelector'
import { useJobStore, type DocType } from '../store/useJobStore'
import { uploadDocument } from '../api/documentApi'
import { createWorkflow } from '../api/workflowApi'
import { getApiErrorMessage } from '../api/errors'

export function UploadPage() {
  const navigate = useNavigate()
  const {
    uploadedFile,
    selectedDocs,
    selectedTemplateByType,
    setDocumentId,
    setWorkflowRuns,
    setStatus,
    setError,
  } = useJobStore()

  const [submitting, setSubmitting] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)

  const templatesReady = selectedDocs.every(
    (d) => Boolean(selectedTemplateByType[d])
  )
  const canSubmit = Boolean(uploadedFile) && selectedDocs.length > 0 && templatesReady

  const handleGenerate = async () => {
    if (!uploadedFile) {
      setValidationError('Please upload a BRD or DOCX file.')
      return
    }
    if (selectedDocs.length === 0) {
      setValidationError('Select at least one document type.')
      return
    }
    const missing = selectedDocs.filter((d) => !selectedTemplateByType[d])
    if (missing.length > 0) {
      setValidationError(
        `Select a template for each output type (missing: ${missing.join(', ')}).`
      )
      return
    }
    setValidationError(null)

    const runs: Partial<Record<DocType, string>> = {}

    try {
      setSubmitting(true)
      setError(null)

      const docRes = await uploadDocument(uploadedFile)
      const document_id = docRes.document_id
      setDocumentId(document_id)

      // Serialize workflow creation to reduce concurrent ingestion on the same document_id.
      for (const doc of selectedDocs) {
        const template_id = selectedTemplateByType[doc]!
        try {
          const created = await createWorkflow({
            document_id,
            template_id,
            start_immediately: true,
          })
          runs[doc] = created.workflow_run_id
        } catch (workflowErr: unknown) {
          const msg = getApiErrorMessage(
            workflowErr,
            'Failed to create workflow run.'
          )
          setWorkflowRuns({ ...runs })
          const detail = `Failed while starting ${doc} (template ${template_id}): ${msg}`
          setError(detail)
          setValidationError(detail)
          setStatus(Object.keys(runs).length ? 'running' : 'idle')
          return
        }
      }

      setWorkflowRuns(runs)
      setStatus('running')

      navigate('/progress')
    } catch (err: unknown) {
      const msg = getApiErrorMessage(err, 'Failed to start pipeline. Check your backend.')
      setError(msg)
      setValidationError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-56px)] bg-white">
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

      <div className="max-w-5xl mx-auto px-8 py-12">
        <div className="space-y-12">
          <section className="animate-slide-up">
            <SectionLabel number="01" label="Upload Document" />
            <FileUploader />
          </section>

          <section className="animate-slide-up" style={{ animationDelay: '0.1s' }}>
            <SectionLabel number="02" label="Output Documents" />
            <DocumentSelector />
          </section>

          <section className="animate-slide-up" style={{ animationDelay: '0.15s' }}>
            <SectionLabel number="03" label="Templates (one per type)" />
            <TemplateSelector />
          </section>

          {validationError && (
            <div className="flex items-center gap-3 border border-red-200 bg-red-50 px-5 py-4 animate-fade-in">
              <AlertCircle size={16} color="#DC2626" />
              <p className="font-body text-sm text-red-600">{validationError}</p>
            </div>
          )}

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

            <div className="flex items-center gap-6 mt-5 flex-wrap">
              <StatusDot active={!!uploadedFile} label="File ready" />
              <StatusDot
                active={selectedDocs.length > 0}
                label={`${selectedDocs.length} doc(s) selected`}
              />
              <StatusDot active={templatesReady} label="Templates for each type" />
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
      <span className="font-body text-xs font-semibold tracking-widest uppercase text-[#6B6B6B]">
        {label}
      </span>
    </div>
  )
}

function StatusDot({ active, label }: { active: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`w-2 h-2 rounded-full transition-colors ${active ? 'bg-black' : 'bg-[#D0D0D0]'}`}
      />
      <span
        className={`font-body text-xs transition-colors ${active ? 'text-black font-medium' : 'text-[#C0C0C0]'}`}
      >
        {label}
      </span>
    </div>
  )
}
