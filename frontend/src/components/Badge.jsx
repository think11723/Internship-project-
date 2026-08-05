import React from 'react'

/**
 * Badge — small label, semantic tone, used for status / category.
 */
const TONES = {
  neutral: 'bg-background-secondary text-gray-800 border-2 border-border-medium',
  brand: 'bg-accent-lime/15 text-primary-700 border-2 border-accent-lime/40',
  success: 'bg-semantic-success/15 text-emerald-700 border-2 border-semantic-success/40',
  warning: 'bg-semantic-warning/15 text-amber-700 border-2 border-semantic-warning/40',
  danger: 'bg-semantic-danger/15 text-red-700 border-2 border-semantic-danger/40',
  info: 'bg-semantic-info/15 text-blue-700 border-2 border-semantic-info/40',
  outline: 'bg-transparent text-gray-800 border-2 border-border-medium',
}

const SIZES = {
  xs: 'px-3 py-1 text-xs gap-2',
  sm: 'px-4 py-2 text-sm gap-2.5',
  md: 'px-5 py-2.5 text-base gap-3',
}

const Badge = ({
  children,
  tone = 'neutral',
  size = 'sm',
  leftIcon: LeftIcon,
  className = '',
  ...rest
}) => (
  <span
    className={[
      'inline-flex items-center rounded-pipeup font-bold transition-all duration-pipeup',
      TONES[tone],
      SIZES[size],
      className,
    ].join(' ')}
    {...rest}
  >
    {LeftIcon && <LeftIcon className="w-4 h-4" aria-hidden="true" />}
    {children}
  </span>
)

export default Badge
