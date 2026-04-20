import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, LayoutTemplate } from 'lucide-react'
import { templateApi } from '../api/templateApi'
import { Template } from '../store/useJobStore'
import { TemplateCard } from '../components/templates/TemplateCard'
import { AddTemplatePanel } from '../components/templates/AddTemplatePanel'

const DOC_TYPES = ['PDD', 'SDD', 'UAT'] as const
type DocType = typeof DOC_TYPES[number]

const TYPE_LABELS: Record<DocType, string> = {
  PDD: 'Product Design Document',
  SDD: 'System Design Document',
  UAT: 'User Acceptance Testing',
}

export function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchTemplates = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await templateApi.listTemplates()
      setTemplates(data)
    } catch {
      setError('Could not load templates. Is the backend running on localhost:8001?')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchTemplates() }, [fetchTemplates])

  const byType = (type: DocType) =>
    templates.filter((t) => (t.type ?? '').toUpperCase() === type)

  return (
    <div className="min-h-[calc(100vh-56px)] bg-white">

      {/* ── Hero strip ── */}
      <div className="bg-black text-white px-8 py-12">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-start gap-4">
            <div className="w-1 h-12 bg-[#FFD400]" />
            <div>
              <p className="font-body text-xs tracking-widest uppercase text-[#FFD400] mb-1 font-medium">
                AI SDLC Platform
              </p>
              <h1 className="font-display font-bold text-5xl uppercase leading-none tracking-tight text-white">
                Template<br />Library
              </h1>
            </div>
          </div>
          <p className="font-body text-sm text-white/50 max-w-lg leading-relaxed mt-6">
            Manage standard and custom document templates. Each template defines the structure
            and sections that the generation engine will produce.
          </p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-8 py-12 space-y-14">

        {/* ── Add Template ── */}
        <section className="animate-slide-up">
          <SectionHeader label="Add New Template" number="01" />
          <AddTemplatePanel onSuccess={fetchTemplates} />
        </section>

        {/* ── Three type lists ── */}
        <section className="animate-slide-up" style={{ animationDelay: '0.1s' }}>
          <div className="flex items-center justify-between mb-8">
            <SectionHeader label="Existing Templates" number="02" />
            <button
              onClick={fetchTemplates}
              disabled={loading}
              className="flex items-center gap-2 border border-[#E5E5E5] px-4 py-2 font-body text-xs hover:border-black transition-colors group"
            >
              <RefreshCw
                size={12}
                className={`transition-transform ${loading ? 'animate-spin' : 'group-hover:rotate-180'}`}
              />
              Refresh
            </button>
          </div>

          {error && (
            <div className="border border-red-200 bg-red-50 px-5 py-4 mb-8 flex items-center gap-3 animate-fade-in">
              <span className="font-body text-sm text-red-600">{error}</span>
              <button onClick={fetchTemplates} className="ml-auto font-body text-xs underline text-red-600">
                Retry
              </button>
            </div>
          )}

          {/* Three columns — one per doc type */}
          <div className="grid grid-cols-3 gap-8">
            {DOC_TYPES.map((type) => {
              const list = byType(type)
              return (
                <div key={type}>
                  {/* Column header */}
                  <div className="flex items-center gap-3 mb-4 pb-3 border-b-2 border-black">
                    <div className="w-7 h-7 bg-[#FFD400] flex items-center justify-center shrink-0">
                      <LayoutTemplate size={13} color="#000" />
                    </div>
                    <div>
                      <p className="font-display font-bold text-2xl uppercase tracking-wide text-black leading-none">
                        {type}
                      </p>
                      <p className="font-body text-[10px] text-[#999] mt-0.5">
                        {TYPE_LABELS[type]}
                      </p>
                    </div>
                    <span className="ml-auto font-display font-bold text-2xl text-[#E5E5E5]">
                      {loading ? '—' : list.length}
                    </span>
                  </div>

                  {/* Template cards */}
                  <div className="space-y-4">
                    {loading ? (
                      <>
                        <SkeletonCard />
                        <SkeletonCard />
                      </>
                    ) : list.length === 0 ? (
                      <EmptyState type={type} />
                    ) : (
                      list.map((tpl) => (
                        <TemplateCard
                          key={tpl.id}
                          template={tpl}
                          onDeleted={fetchTemplates}
                        />
                      ))
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>

      </div>
    </div>
  )
}

/* ── Sub-components ────────────────────────────────────── */

function SectionHeader({ number, label }: { number: string; label: string }) {
  return (
    <div className="flex items-center gap-3 mb-6">
      <span className="font-display font-bold text-3xl text-[#FFD400] leading-none">{number}</span>
      <div className="h-px flex-1 bg-[#E5E5E5]" />
      <span className="font-body text-xs font-semibold tracking-widest uppercase text-[#6B6B6B]">
        {label}
      </span>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="border border-[#E5E5E5] p-5 animate-pulse">
      <div className="h-3 bg-[#E5E5E5] w-16 mb-3 rounded" />
      <div className="h-5 bg-[#E5E5E5] w-3/4 mb-2 rounded" />
      <div className="h-3 bg-[#E5E5E5] w-full mb-1 rounded" />
      <div className="h-3 bg-[#E5E5E5] w-2/3 mb-4 rounded" />
      <div className="h-8 bg-[#E5E5E5] w-full rounded" />
    </div>
  )
}

function EmptyState({ type }: { type: string }) {
  return (
    <div className="border-2 border-dashed border-[#E5E5E5] p-8 text-center">
      <p className="font-display font-bold text-lg uppercase text-[#D0D0D0] tracking-wide mb-1">
        No {type} Templates
      </p>
      <p className="font-body text-xs text-[#C0C0C0]">
        Upload a custom template above to get started.
      </p>
    </div>
  )
}
