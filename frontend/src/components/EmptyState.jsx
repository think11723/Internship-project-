import React from 'react'
import Button from './Button'

/**
 * EmptyState — friendly, actionable placeholder for every "no data" case.
 *
 * Every EmptyState should:
 *   - tell the user what is missing
 *   - tell them why it matters
 *   - offer a concrete next step
 */
const EmptyState = ({
  icon: Icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  children,
  className = '',
}) => (
  <div className={`empty-state ${className}`}>
    {Icon && (
      <div className="flex h-16 w-16 items-center justify-center rounded-pipeup-lg bg-primary-500/15 text-primary-700 ring-2 ring-primary-500/30">
        <Icon className="h-8 w-8" aria-hidden="true" />
      </div>
    )}
    <div className="space-y-2">
      {title && (
        <h3 className="text-xl font-bold text-dark-primary">{title}</h3>
      )}
      {description && (
        <p className="mx-auto max-w-md text-sm font-medium leading-6 text-gray-700">
          {description}
        </p>
      )}
    </div>
    {children}
    {(primaryAction || secondaryAction) && (
      <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
        {primaryAction}
        {secondaryAction}
      </div>
    )}
  </div>
)

export default EmptyState
