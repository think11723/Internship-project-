import React from 'react'

const Card = ({
  children,
  className = '',
  hover = false,
  glass = false,
  padding = 'lg',
  as: Component = 'div',
  ...rest
}) => {
  const baseStyles = glass
    ? 'bg-background-card/80 backdrop-blur-md border border-border-light rounded-pipeup shadow-pipeup'
    : 'bg-background-card border border-border-light rounded-pipeup shadow-pipeup'
  // Sprint-9 polish: standardized hover interaction across the app.
  // - 400ms ease (matches every other transition in the app)
  // - subtle upward lift (3px)
  // - shadow upgrade (pipeup-lg)
  // - soft orange accent border (accent-lime/50) on hover — only
  //   visible to the eye, not loud
  // - active:scale-[0.99] for tactile click feedback
  // Sprint 15: focus-within ring for keyboard users — keeps the
  //   border treatment consistent with the global focus-visible rule
  //   while preserving the existing rest-state visual identity.
  const hoverStyles = hover
    ? 'transition-all duration-pipeup ease-out hover:-translate-y-0.5 hover:shadow-pipeup-lg hover:border-accent-lime/50 active:scale-[0.99] focus-within:border-accent-lime/60 focus-within:shadow-pipeup-lg'
    : 'focus-within:border-accent-lime/40'

  const paddings = {
    sm: 'p-5',
    md: 'p-6',
    lg: 'p-8',
    xl: 'p-10',
  }

  return (
    <Component
      className={`${baseStyles} ${hoverStyles} ${paddings[padding]} ${className}`}
      {...rest}
    >
      {children}
    </Component>
  )
}

export default Card
