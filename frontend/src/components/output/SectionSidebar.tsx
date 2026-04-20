import { useJobStore } from '../../store/useJobStore'
import { ChevronRight } from 'lucide-react'

export function SectionSidebar() {
  const {
    activDoc,
    activeSectionId,
    documents,
    workflowDetailByType,
    setActiveSectionId,
    setSectionContent,
  } = useJobStore()

  const currentDoc = documents.find((d) => d.type === activDoc)
  const assembled = activDoc ? workflowDetailByType[activDoc]?.assembled_document : null

  const rows =
    assembled?.sections?.map((s) => ({ section_id: s.section_id, title: s.title })) ??
    currentDoc?.sections ??
    []

  const handleSelect = (sectionId: string) => {
    if (!activDoc || sectionId === activeSectionId) return
    setActiveSectionId(sectionId)
    const row = assembled?.sections?.find((s) => s.section_id === sectionId)
    const content = row?.content ?? null
    setSectionContent(content ?? '_No content for this section._')
  }

  if (rows.length === 0) {
    return (
      <div className="p-6 text-center">
        <p className="font-body text-xs text-[#999]">No sections available.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <div className="px-5 py-4 border-b border-[#E5E5E5]">
        <p className="font-body text-[10px] tracking-widest uppercase text-[#999] font-medium">
          Sections
        </p>
      </div>
      <div className="flex-1 overflow-y-auto">
        {rows.map((section, i) => {
          const active = activeSectionId === section.section_id
          return (
            <button
              key={section.section_id}
              type="button"
              onClick={() => handleSelect(section.section_id)}
              className={`w-full text-left px-5 py-3.5 flex items-center gap-3 border-b border-[#F0F0F0] transition-all group ${
                active ? 'bg-black text-white' : 'hover:bg-[#F7F7F7] text-black'
              }`}
            >
              <span
                className={`font-body text-[10px] font-medium w-5 shrink-0 ${
                  active ? 'text-[#FFD400]' : 'text-[#C0C0C0]'
                }`}
              >
                {String(i + 1).padStart(2, '0')}
              </span>
              <span
                className={`font-body text-sm flex-1 leading-snug ${
                  active ? 'text-white font-medium' : 'text-[#1A1A1A]'
                }`}
              >
                {section.title}
              </span>
              <ChevronRight
                size={13}
                className={`shrink-0 transition-transform ${
                  active ? 'text-[#FFD400]' : 'text-[#D0D0D0] group-hover:text-black'
                }`}
              />
            </button>
          )
        })}
      </div>
    </div>
  )
}
