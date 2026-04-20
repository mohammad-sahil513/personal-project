import { useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, RefreshCw, AlertCircle } from 'lucide-react'
import { ProgressBar } from '../components/progress/ProgressBar'
import { useJobStore, type DocType } from '../store/useJobStore'
import { getWorkflowStatus, getWorkflow } from '../api/workflowApi'

function backendStatusUi(s: string | undefined): 'running' | 'completed' | 'failed' {
  const u = (s || '').toUpperCase()
  if (u === 'FAILED') return 'failed'
  if (u === 'COMPLETED') return 'completed'
  return 'running'
}

export function ProgressPage() {
  const navigate = useNavigate()
  const {
    selectedDocs,
    workflowRunByType,
    status,
    progress,
    currentStep,
    errorMessage,
    perTypeProgress,
    perTypeStep,
    setProgress,
    setStatus,
    setPerTypeProgress,
    setDocuments,
    setActiveDoc,
    setError,
    setWorkflowDetail,
    documents,
  } = useJobStore()

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadCompletedOutputs = useCallback(() => {
    ;(async () => {
      const { selectedDocs: docs, workflowRunByType: runs, setWorkflowDetail, setDocuments, setActiveDoc } =
        useJobStore.getState()
      const out: { type: DocType; sections: { section_id: string; title: string }[] }[] = []
      for (const doc of docs) {
        const runId = runs[doc]
        if (!runId) continue
        const w = await getWorkflow(runId)
        setWorkflowDetail(doc, w)
        out.push({
          type: doc,
          sections:
            w.assembled_document?.sections?.map((s) => ({
              section_id: s.section_id,
              title: s.title,
            })) ?? [],
        })
      }
      setDocuments(out)
      if (out.length > 0) setActiveDoc(out[0].type)
    })().catch(() => {})
  }, [])

  const poll = useCallback(async () => {
    const { selectedDocs: docs, workflowRunByType: runs } = useJobStore.getState()
    if (docs.length === 0) return
    try {
      const results = await Promise.all(
        docs.map(async (doc) => {
          const id = runs[doc]
          if (!id) return { doc, st: null as Awaited<ReturnType<typeof getWorkflowStatus>> | null }
          const st = await getWorkflowStatus(id)
          return { doc, st }
        })
      )

      const progressValues: number[] = []
      const stepParts: string[] = []
      let anyFailed = false

      for (const { doc, st } of results) {
        if (!st) continue
        const p = st.overall_progress_percent ?? 0
        progressValues.push(p)
        const label = st.current_step_label || st.current_phase || '…'
        stepParts.push(`${doc}: ${label}`)
        setPerTypeProgress(doc, p, label)

        const u = backendStatusUi(st.status)
        if (u === 'failed') anyFailed = true
      }

      const avgProgress = progressValues.length
        ? Math.round(progressValues.reduce((sum, value) => sum + value, 0) / progressValues.length)
        : 0

      setProgress(avgProgress, stepParts.join(' · '))

      if (anyFailed) {
        const failedDoc = results.find(({ st }) => st && backendStatusUi(st.status) === 'failed')
        setError(
          failedDoc?.st
            ? `Pipeline failed (${failedDoc.doc}). Check backend logs.`
            : 'Pipeline failed. Check backend logs.'
        )
        setStatus('failed')
        if (intervalRef.current) clearInterval(intervalRef.current)
        intervalRef.current = null
        return
      }

      const allCompleted =
        results.length >= docs.length &&
        results.every(({ st }) => st && backendStatusUi(st.status) === 'completed')

      if (allCompleted && docs.every((d) => runs[d])) {
        setStatus('completed')
        await loadCompletedOutputs()
        if (intervalRef.current) clearInterval(intervalRef.current)
        intervalRef.current = null
      } else {
        setStatus('running')
      }
    } catch {
      // network hiccup
    }
  }, [setProgress, setPerTypeProgress, setStatus, setError, loadCompletedOutputs])

  const startPolling = useCallback(() => {
    poll()
    intervalRef.current = setInterval(poll, 2500)
  }, [poll])

  const stopPolling = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }

  useEffect(() => {
    const { selectedDocs: docs, workflowRunByType: runs } = useJobStore.getState()
    const hasRuns = docs.length > 0 && docs.every((d) => runs[d])
    if (!hasRuns) {
      navigate('/')
      return
    }
    if (status === 'running') {
      startPolling()
    }
    return () => stopPolling()
  }, [navigate, status, startPolling])

  useEffect(() => {
    if (status === 'completed' && documents.length === 0) {
      loadCompletedOutputs()
    }
  }, [status, documents.length, loadCompletedOutputs])

  const handleViewOutput = () => navigate('/output')

  const docLabels = selectedDocs.length ? selectedDocs : (['PDD', 'SDD', 'UAT'] as DocType[])

  return (
    <div className="min-h-[calc(100vh-56px)] bg-white flex flex-col">
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
              <div className="flex flex-wrap items-center gap-6 mb-12 animate-fade-in">
                {docLabels.map((doc) => {
                  const done = status === 'completed'
                  const tp = perTypeProgress[doc]
                  return (
                    <div key={doc} className="flex items-center gap-2">
                      <div
                        className={`w-2 h-2 rounded-full transition-colors duration-500 ${
                          done ? 'bg-[#FFD400]' : 'bg-[#D0D0D0] animate-pulse'
                        }`}
                      />
                      <span className="font-display font-bold text-lg uppercase text-black tracking-wide">
                        {doc}
                      </span>
                      {tp !== undefined && status === 'running' && (
                        <span className="font-body text-xs text-[#999]">{tp}%</span>
                      )}
                    </div>
                  )
                })}
              </div>

              <ProgressBar />

              {status === 'running' && (
                <div className="mt-4 space-y-1 font-body text-xs text-[#6B6B6B] max-h-24 overflow-y-auto">
                  {selectedDocs.map((doc) =>
                    perTypeStep[doc] ? (
                      <p key={doc}>
                        <span className="font-semibold text-black">{doc}:</span> {perTypeStep[doc]}
                      </p>
                    ) : null
                  )}
                </div>
              )}

              {status === 'running' && progress < 100 && (
                <p className="font-body text-xs text-[#C0C0C0] mt-6 animate-fade-in">
                  {currentStep || 'This may take a few minutes depending on document length.'}
                </p>
              )}

              {status === 'completed' && (
                <div className="mt-12 animate-slide-up">
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-6 h-6 bg-[#FFD400] flex items-center justify-center">
                      <svg width="12" height="10" viewBox="0 0 12 10" fill="none">
                        <path
                          d="M1 5L4.5 8.5L11 1"
                          stroke="#000"
                          strokeWidth="2"
                          strokeLinecap="square"
                        />
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
