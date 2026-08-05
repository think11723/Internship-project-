import React from 'react'

const Loader = ({ size = 'medium', className = '', label = 'Loading' }) => {
  const sizes = {
    small: 'w-6 h-6 border-3',
    medium: 'w-12 h-12 border-4',
    large: 'w-20 h-20 border-5',
  }

  const ringSizes = {
    small: 'border-2',
    medium: 'border-4',
    large: 'border-[5px]',
  }

  return (
    <div
      className={`flex items-center justify-center ${className}`}
      role="status"
      aria-label={label}
    >
      <span
        className={`loader ${sizes[size]} ${ringSizes[size]}`}
        aria-hidden="true"
      />
    </div>
  )
}

export default Loader
