import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useJobStore } from '../../store/useJobStore'
import { FileText } from 'lucide-react'

function MarkdownPage({ content }: { content: string }) {
  return (
    <div className="bg-white w-full max-w-[820px] mx-auto shadow-[0_1px_4px_rgba(0,0,0,0.08)] px-16 py-14 mb-8">
      <div className="docx-prose">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </div>
  )
}

export function DocxViewer() {
  const { sectionContent, activeSectionId } = useJobStore()

  if (!activeSectionId) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-8">
        <div className="w-14 h-14 bg-[#F7F7F7] flex items-center justify-center">
          <FileText size={24} color="#C0C0C0" />
        </div>
        <p className="font-display font-bold text-xl uppercase text-[#C0C0C0] tracking-wide">
          Select a Section
        </p>
        <p className="font-body text-sm text-[#999] max-w-xs">
          Choose a section from the left panel to view generated content.
        </p>
      </div>
    )
  }

  if (!sectionContent) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="font-body text-sm text-[#999]">No content available.</p>
      </div>
    )
  }

  // Split by page breaks
  const pages = sectionContent.split('<!-- PAGE_BREAK -->')

  return (
    <div className="bg-[#F0F0F0] flex-1 overflow-y-auto py-10 px-6 animate-fade-in">
      {pages.map((pageContent, i) => (
        <div key={i}>
          <MarkdownPage content={pageContent.trim()} />
          {i < pages.length - 1 && (
            <hr className="page-break-divider my-2" />
          )}
        </div>
      ))}
    </div>
  )
}
