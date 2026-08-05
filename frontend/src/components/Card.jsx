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
  const hoverStyles = hover
    ? 'transition-all duration-pipeup hover:shadow-pipeup-lg hover:-translate-y-0.5'
    : ''

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
