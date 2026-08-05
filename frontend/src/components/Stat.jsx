import React from 'react'

/**
 * Stat — Pipeup-style large display number with optional label and trend.
 * Used in the executive dashboard for Career Snapshot cards.
 */
const Stat = ({
  label,
  value,
  hint,
  accent = false,
  trend,
  className = '',
  ...rest
}) => (
  <div
    className={[
      'bg-background-card border border-border-light rounded-pipeup p-10 transition-all duration-pipeup hover:shadow-pipeup-lg',
      accent
        ? 'border-accent-lime/30 bg-accent-lime/5 shadow-pipeup-glow'
        : '',
      className,
    ].join(' ')}
    {...rest}
  >
    <div className="flex items-center justify-between">
      <p className="text-sm font-semibold uppercase tracking-widest text-muted-medium">
        {label}
      </p>
      {trend && (
        <span
          className={[
            'inline-flex items-center rounded-full px-4 py-2 text-sm font-semibold',
            trend.direction === 'up'
              ? 'bg-semantic-success/10 text-semantic-success border border-semantic-success/20'
              : trend.direction === 'down'
              ? 'bg-semantic-danger/10 text-semantic-danger border border-semantic-danger/20'
              : 'bg-background-secondary text-muted-medium border border-border-light rounded-full',
          ].join(' ')}
        >
          {trend.label}
        </span>
      )}
    </div>
    <p
      className={[
        'mt-8 text-5xl font-bold font-mono tracking-tight',
        accent ? 'text-accent-lime' : 'text-dark-primary',
      ].join(' ')}
    >
      {value}
    </p>
    {hint && <p className="mt-4 text-base text-muted-medium">{hint}</p>}
  </div>
)

export default Stat
