import React from 'react'
import { Search, AlertCircle } from 'lucide-react'

/**
 * Input — Pipeup-style text input with leading icon, error state, and focus ring.
 */
const Input = React.forwardRef(function Input(
  {
    label,
    hint,
    error,
    leftIcon: LeftIcon,
    rightIcon: RightIcon,
    className = '',
    inputClassName = '',
    id,
    ...rest
  },
  ref
) {
  const reactId = React.useId()
  const inputId = id || `input-${reactId}`
  return (
    <div className={['w-full', className].join(' ')}>
      {label && (
        <label
          htmlFor={inputId}
          className="mb-4 block text-sm font-semibold uppercase tracking-widest text-muted-medium"
        >
          {label}
        </label>
      )}
      <div className="relative">
        {LeftIcon && (
          <LeftIcon
            className="pointer-events-none absolute left-6 top-1/2 h-6 w-6 -translate-y-1/2 text-muted-medium"
            aria-hidden="true"
          />
        )}
        <input
          ref={ref}
          id={inputId}
          className={[
            'w-full rounded-pipeup border border-border-medium bg-background-secondary px-6 py-4 text-base text-dark-primary placeholder:text-muted-light transition-all duration-pipeup focus:border-accent-lime focus:ring-2 focus:ring-accent-lime/20 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50',
            LeftIcon ? 'pl-14' : 'px-6',
            RightIcon ? 'pr-14' : 'pr-6',
            error
              ? 'border-semantic-danger focus:border-semantic-danger focus:ring-semantic-danger/30'
              : '',
            inputClassName,
          ].join(' ')}
          {...rest}
        />
        {RightIcon && (
          <RightIcon
            className="pointer-events-none absolute right-6 top-1/2 h-6 w-6 -translate-y-1/2 text-muted-medium"
            aria-hidden="true"
          />
        )}
      </div>
      {(hint || error) && (
        <p
          className={[
            'mt-4 flex items-center gap-2 text-sm',
            error ? 'text-semantic-danger' : 'text-muted-medium',
          ].join(' ')}
        >
          {error ? <AlertCircle className="h-5 w-5" aria-hidden="true" /> : null}
          {error || hint}
        </p>
      )}
    </div>
  )
})

export default Input
export { Search }
