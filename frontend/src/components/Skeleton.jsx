import React from 'react'

/**
 * Skeleton — loading placeholder with shimmer effect
 */
const Skeleton = ({ className = '', variant = 'default' }) => {
  const variants = {
    default: 'h-4 w-full',
    text: 'h-4 w-3/4',
    heading: 'h-8 w-1/2',
    circle: 'h-12 w-12 rounded-full',
    avatar: 'h-10 w-10 rounded-full',
    card: 'h-32 w-full',
  }
  
  return (
    <div className={`skeleton ${variants[variant]} ${className}`} />
  )
}

export default Skeleton