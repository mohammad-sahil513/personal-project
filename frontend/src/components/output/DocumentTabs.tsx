import { useJobStore, type DocType } from '../../store/useJobStore'

export function DocumentTabs() {
  const {
    documents,
    activDoc,
    setActiveDoc,
    workflowDetailByType,
    setActiveSectionId,
    setSectionContent,
  } = useJobStore()

  if (!documents.length) return null

  const selectTab = (type: DocType) => {
    setActiveDoc(type)
    const w = workflowDetailByType[type]
    const first = w?.assembled_document?.sections?.[0]
    if (first) {
      setActiveSectionId(first.section_id)
      setSectionContent(first.content ?? '_No content for this section._')
    } else {
      setActiveSectionId(null)
      setSectionContent(null)
    }
  }

  return (
    <div className="flex items-end border-b border-[#E5E5E5]">
      {documents.map(({ type }) => {
        const active = activDoc === type
        return (
          <button
            key={type}
            type="button"
            onClick={() => selectTab(type as DocType)}
            className={`relative px-8 py-4 font-display font-bold text-base uppercase tracking-widest transition-colors ${
              active
                ? 'text-black border-b-2 border-black -mb-px'
                : 'text-[#999] hover:text-black border-b-2 border-transparent -mb-px'
            }`}
          >
            {active && (
              <span className="absolute bottom-0 left-0 w-full h-0.5 bg-[#FFD400] -mb-0.5" />
            )}
            {type}
          </button>
        )
      })}
    </div>
  )
}
