import { useJobStore, DocType } from '../../store/useJobStore'

const DOC_OPTIONS: { type: DocType; label: string; desc: string }[] = [
  { type: 'PDD', label: 'PDD', desc: 'Product Design Document' },
  { type: 'SDD', label: 'SDD', desc: 'System Design Document' },
  { type: 'UAT', label: 'UAT', desc: 'User Acceptance Testing' },
]

export function DocumentSelector() {
  const { selectedDocs, toggleDoc, setSelectedDocs } = useJobStore()

  const allSelected = selectedDocs.length === DOC_OPTIONS.length

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="font-body text-xs font-medium tracking-widest text-[#6B6B6B] uppercase">
          Documents to Generate
        </p>
        <button
          onClick={() =>
            allSelected
              ? setSelectedDocs([])
              : setSelectedDocs(DOC_OPTIONS.map((d) => d.type))
          }
          className="font-body text-xs text-black underline"
        >
          {allSelected ? 'Deselect all' : 'Select all'}
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {DOC_OPTIONS.map(({ type, label, desc }) => {
          const checked = selectedDocs.includes(type)
          return (
            <button
              key={type}
              onClick={() => toggleDoc(type)}
              className={`p-4 border-2 text-left transition-all ${
                checked
                  ? 'border-black bg-black text-white'
                  : 'border-[#E5E5E5] bg-white text-black hover:border-black'
              }`}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <span className={`font-display font-bold text-2xl tracking-wide ${checked ? 'text-[#FFD400]' : 'text-black'}`}>
                  {label}
                </span>
                <div className={`w-5 h-5 border-2 flex items-center justify-center shrink-0 mt-1 transition-colors ${
                  checked ? 'border-[#FFD400] bg-[#FFD400]' : 'border-[#D0D0D0] bg-white'
                }`}>
                  {checked && (
                    <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                      <path d="M1 4L3.5 6.5L9 1" stroke="#000" strokeWidth="1.8" strokeLinecap="square"/>
                    </svg>
                  )}
                </div>
              </div>
              <p className={`font-body text-xs ${checked ? 'text-white/70' : 'text-[#6B6B6B]'}`}>
                {desc}
              </p>
            </button>
          )
        })}
      </div>
    </div>
  )
}
