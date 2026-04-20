import { useNavigate, useLocation } from 'react-router-dom'
import { useJobStore } from '../../store/useJobStore'

export function Navbar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { status, reset } = useJobStore()

  const jobSteps = [
    { label: '01 UPLOAD',   path: '/' },
    { label: '02 GENERATE', path: '/progress' },
    { label: '03 REVIEW',   path: '/output' },
  ]

  const handleLogo = () => {
    reset()
    navigate('/')
  }

  const isTemplatesPage = location.pathname === '/templates'

  return (
    <nav className="bg-black text-white h-14 flex items-center px-8 sticky top-0 z-50 gap-8">
      {/* Logo */}
      <button onClick={handleLogo} className="flex items-center gap-2 group mr-auto">
        <div className="w-7 h-7 bg-[#FFD400] flex items-center justify-center shrink-0">
          <span className="font-display font-bold text-black text-xs leading-none">AI</span>
        </div>
        <span className="font-display font-bold text-base tracking-wide uppercase text-white">
          SDLC<span className="text-[#FFD400]">.</span>
        </span>
      </button>

      {/* Templates link — always accessible */}
      <button
        onClick={() => navigate('/templates')}
        className={`font-body text-xs font-medium tracking-widest transition-colors border-b-2 pb-0.5 ${
          isTemplatesPage
            ? 'text-[#FFD400] border-[#FFD400]'
            : 'text-white/50 border-transparent hover:text-white/80'
        }`}
      >
        TEMPLATES
      </button>

      {/* Divider */}
      <div className="w-px h-4 bg-white/20" />

      {/* Job flow steps */}
      {jobSteps.map((step, i) => {
        const active = location.pathname === step.path && !isTemplatesPage
        const isAccessible =
          step.path === '/' ||
          (step.path === '/progress' &&
            ['created', 'uploaded', 'running', 'completed', 'failed'].includes(status)) ||
          (step.path === '/output' && status === 'completed')

        return (
          <button
            key={i}
            onClick={() => isAccessible && navigate(step.path)}
            disabled={!isAccessible}
            className={`font-body text-xs font-medium tracking-widest transition-colors ${
              active
                ? 'text-[#FFD400]'
                : isAccessible
                ? 'text-white/50 hover:text-white/80'
                : 'text-white/20 cursor-not-allowed'
            }`}
          >
            {step.label}
          </button>
        )
      })}
    </nav>
  )
}
