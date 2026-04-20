import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, RefreshCw, AlertCircle } from 'lucide-react'
import { ProgressBar } from '../components/progress/ProgressBar'
import { useJobStore } from '../store/useJobStore'
import { jobApi } from '../api/jobApi'
import { outputApi } from '../api/outputApi'

const STAGE_LABELS: Record<string, string> = {
  ingestion: 'Ingesting document',
  stage_8: 'Section segmentation',
  stage_9: 'Knowledge extraction',
  stage_10: 'Process graph construction',
  stage_11: 'Validation',
  stage_12: 'Chunking',
  stage_13: 'Vector indexing',
  template_resolution: 'Resolving template',
  generation: 'Generating content',
  pdd_generation: 'Generating PDD',
  sdd_generation: 'Generating SDD',
  uat_generation: 'Generating UAT',
  completed: 'All done',
}

function formatStep(raw: string): string {
  return STAGE_LABELS[raw] ?? raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function ProgressPage() {
  const navigate = useNavigate()
  const {
    jobId,
    status,
    progress,
    currentStep,
    errorMessage,
    setProgress,
    setStatus,
    setDocuments,
    setActiveDoc,
    setError,
    documents,
  } = useJobStore()

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const poll = async () => {
    if (!jobId) return
    try {
      const data = await jobApi.getProgress(jobId)
      const step = formatStep(data.current_step)
      setProgress(data.progress_percent, step)
      setStatus(data.status)

      if (data.status === 'completed') {
        stopPolling()
        // Load output structure
        try {
          const output = await outputApi.getDocuments(jobId)
          setDocuments(output.documents)
          if (output.documents.length > 0) {
            setActiveDoc(output.documents[0].type)
          }
        } catch {
          // Documents might load fine on output page
        }
      }

      if (data.status === 'failed') {
        stopPolling()
        setError('Pipeline failed. Please check your backend logs.')
      }
    } catch {
      // Network hiccup — keep polling
    }
  }

  const startPolling = () => {
    poll()
    intervalRef.current = setInterval(poll, 2500)
  }

  const stopPolling = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }

  useEffect(() => {
    if (!jobId) {
      navigate('/')
      return
    }
    if (status === 'running' || status === 'uploaded' || status === 'created') {
      startPolling()
    } else if (status === 'completed') {
      // Already completed (e.g. navigated back)
    }
    return () => stopPolling()
  }, [jobId])

  const handleViewOutput = () => navigate('/output')

  return (
    <div className="min-h-[calc(100vh-56px)] bg-white flex flex-col">
      {/* Header band */}
      <div className="bg-black px-8 py-10">
        <div className="max-w-3xl mx-auto">
          <p className="font-body text-xs tracking-widest uppercase text-[#FFD400] mb-2 font-medium">
            Pipeline Running
          </p>
          <h1 className="font-display font-bold text-4xl uppercase text-white tracking-tight">
            Generating Documents
          </h1>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex items-center justify-center px-8">
        <div className="w-full max-w-3xl py-20">

          {status === 'failed' ? (
            <div className="animate-fade-in">
              <div className="flex items-start gap-4 border border-red-200 bg-red-50 p-6 mb-8">
                <AlertCircle size={20} color="#DC2626" className="shrink-0 mt-0.5" />
                <div>
                  <p className="font-body font-semibold text-red-700 text-sm mb-1">
                    Generation Failed
                  </p>
                  <p className="font-body text-sm text-red-600">
                    {errorMessage ?? 'An unexpected error occurred. Please check your backend.'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => navigate('/')}
                className="flex items-center gap-3 px-8 py-4 bg-black text-[#FFD400] font-display font-bold uppercase tracking-widest hover:bg-[#1A1A1A] transition-colors"
              >
                <RefreshCw size={16} />
                Try Again
              </button>
            </div>
          ) : (
            <>
              {/* Big doc labels */}
              <div className="flex items-center gap-6 mb-12 animate-fade-in">
                {['PDD', 'SDD', 'UAT'].map((doc) => (
                  <div key={doc} className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full transition-colors duration-500 ${
                      status === 'completed' ? 'bg-[#FFD400]' : 'bg-[#D0D0D0] animate-pulse'
                    }`} />
                    <span className="font-display font-bold text-lg uppercase text-black tracking-wide">
                      {doc}
                    </span>
                  </div>
                ))}
              </div>

              {/* Progress bar */}
              <ProgressBar />

              {/* Elapsed hint */}
              {status === 'running' && progress < 100 && (
                <p className="font-body text-xs text-[#C0C0C0] mt-6 animate-fade-in">
                  This may take a few minutes depending on document length and selected models.
                </p>
              )}

              {/* CTA when complete */}
              {status === 'completed' && (
                <div className="mt-12 animate-slide-up">
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-6 h-6 bg-[#FFD400] flex items-center justify-center">
                      <svg width="12" height="10" viewBox="0 0 12 10" fill="none">
                        <path d="M1 5L4.5 8.5L11 1" stroke="#000" strokeWidth="2" strokeLinecap="square"/>
                      </svg>
                    </div>
                    <span className="font-display font-bold text-xl uppercase tracking-wide text-black">
                      {documents.length} Document{documents.length !== 1 ? 's' : ''} Ready
                    </span>
                  </div>
                  <button
                    onClick={handleViewOutput}
                    className="group flex items-center gap-4 px-10 py-5 bg-black text-[#FFD400] font-display font-bold text-xl uppercase tracking-widest hover:bg-[#FFD400] hover:text-black transition-all"
                  >
                    View &amp; Download
                    <ArrowRight size={20} className="transition-transform group-hover:translate-x-1" />
                  </button>
                </div>
              )}
            </>
          )}

        </div>
      </div>
    </div>
  )
}
