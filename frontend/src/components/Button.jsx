import React from 'react'

const Button = ({
  children,
  variant = 'primary',
  size = 'medium',
  disabled = false,
  onClick,
  className = '',
  leftIcon: LeftIcon,
  rightIcon: RightIcon,
  type = 'button',
  ariaLabel,
}) => {
  const baseStyles = 'relative inline-flex items-center justify-center gap-2 font-bold transition-all duration-pipeup focus:outline-none focus:ring-2 focus:ring-accent-lime/60 focus:ring-offset-2 focus:ring-offset-background-primary disabled:opacity-50 disabled:cursor-not-allowed'

  const variants = {
    primary: 'bg-accent-lime text-dark-primary rounded-pipeup shadow-pipeup hover:bg-accent-limeHover hover:shadow-pipeup-lg hover:-translate-y-0.5 active:scale-95',
    secondary: 'bg-background-card border border-border-medium text-dark-primary rounded-pipeup hover:bg-background-secondary hover:border-accent-lime/60 hover:shadow-pipeup active:scale-95',
    ghost: 'text-gray-700 hover:text-dark-primary hover:bg-background-secondary rounded-pipeup active:scale-95',
    danger: 'bg-semantic-danger text-background-primary rounded-pipeup shadow-pipeup hover:bg-semantic-danger/90 hover:shadow-pipeup-lg hover:-translate-y-0.5 active:scale-95',
    black: 'bg-dark-primary text-background-primary rounded-pipeup hover:bg-dark-secondary active:scale-95',
  }

  const sizes = {
    small: 'px-5 py-2.5 text-xs',
    medium: 'px-7 py-3 text-sm',
    large: 'px-8 py-4 text-base',
    xl: 'px-12 py-6 text-xl',
  }

  return (
    <button
      type={type}
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled}
      onClick={onClick}
      aria-label={ariaLabel}
      aria-disabled={disabled || undefined}
    >
      {LeftIcon && <LeftIcon className="w-4 h-4" aria-hidden="true" />}
      {children}
      {RightIcon && <RightIcon className="w-4 h-4" aria-hidden="true" />}
    </button>
  )
}

export default Button
