import { useJobStore } from '../../store/useJobStore'

export function ProgressBar() {
  const { progress, currentStep, status } = useJobStore()

  const isFailed = status === 'failed'
  const isComplete = status === 'completed'

  return (
    <div className="w-full animate-fade-in">
      {/* Bar track */}
      <div className="h-1.5 bg-[#E5E5E5] w-full relative overflow-hidden">
        <div
          className={`h-full transition-all duration-700 ease-out ${
            isFailed ? 'bg-red-500' : isComplete ? 'bg-[#FFD400]' : 'bg-black'
          }`}
          style={{ width: `${progress}%` }}
        />
        {/* Shimmer while running */}
        {status === 'running' && (
          <div
            className="absolute top-0 left-0 h-full w-24 bg-gradient-to-r from-transparent via-white/40 to-transparent animate-pulse-bar"
            style={{ left: `${Math.max(0, progress - 15)}%` }}
          />
        )}
      </div>

      {/* Labels */}
      <div className="flex items-center justify-between mt-4">
        <p className="font-body text-sm text-[#6B6B6B]">
          {isFailed
            ? 'Generation failed'
            : isComplete
            ? 'All documents ready'
            : currentStep || 'Initialising pipeline…'}
        </p>
        <span className={`font-display font-bold text-3xl tracking-tight ${
          isFailed ? 'text-red-500' : isComplete ? 'text-black' : 'text-black'
        }`}>
          {progress}
          <span className="text-[#FFD400]">%</span>
        </span>
      </div>
    </div>
  )
}
