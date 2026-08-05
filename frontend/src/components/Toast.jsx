import React, { useEffect } from 'react'
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react'

/**
 * Toast — premium notification component
 */
const Toast = ({
  message,
  type = 'info',
  onClose,
  duration = 5000,
  className = ''
}) => {
  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(onClose, duration)
      return () => clearTimeout(timer)
    }
  }, [duration, onClose])

  const icons = {
    success: CheckCircle,
    error: AlertCircle,
    warning: AlertCircle,
    info: Info,
  }

  const tones = {
    success: 'border-semantic-success/40 bg-semantic-success/10 text-emerald-700',
    error: 'border-semantic-danger/40 bg-semantic-danger/10 text-red-700',
    warning: 'border-semantic-warning/40 bg-semantic-warning/10 text-amber-700',
    info: 'border-semantic-info/40 bg-semantic-info/10 text-blue-700',
  }

  const Icon = icons[type]

  return (
    <div
      role="alert"
      aria-live="polite"
      className={`toast ${tones[type]} ${className}`}
    >
      <Icon className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
      <p className="flex-1 text-sm font-semibold">{message}</p>
      <button
        onClick={onClose}
        className="ml-3 p-1 rounded hover:bg-surface-elevated/50 transition-colors"
        aria-label="Dismiss notification"
      >
        <X className="w-4 h-4" aria-hidden="true" />
      </button>
    </div>
  )
}

export default Toast
