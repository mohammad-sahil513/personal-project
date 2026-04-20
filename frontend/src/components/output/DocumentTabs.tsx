import { useJobStore, DocType } from '../../store/useJobStore'

export function DocumentTabs() {
  const { documents, activDoc, setActiveDoc } = useJobStore()

  if (!documents.length) return null

  return (
    <div className="flex items-end border-b border-[#E5E5E5]">
      {documents.map(({ type }) => {
        const active = activDoc === type
        return (
          <button
            key={type}
            onClick={() => setActiveDoc(type as DocType)}
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
