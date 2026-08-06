import React from 'react'
import { Link } from 'react-router-dom'

/**
 * The FundFlow AI brand mark — logo tile plus wordmark.
 *
 * Shared by the top navbar and the mobile drawer so both show the same
 * branding from one definition.
 *
 * @param {object}   props
 * @param {string}   [props.wordmarkClassName] display utilities for the
 *   wordmark block. Defaults to the navbar's behaviour (hidden on the
 *   narrowest screens, where the logo tile alone stands in). The drawer
 *   passes `flex` because it has room to always show the full wordmark.
 * @param {Function} [props.onNavigate] called when the brand link is
 *   activated — the drawer passes its close handler.
 */
const Brand = ({ wordmarkClassName = 'hidden sm:flex', onNavigate }) => (
  <Link
    to="/"
    onClick={onNavigate}
    className="flex items-center gap-3 group"
    aria-label="FundFlow AI home"
  >
    <div className="w-10 h-10 bg-accent-lime rounded-pipeup flex items-center justify-center shadow-pipeup group-hover:shadow-pipeup-lg transition-all duration-pipeup group-hover:scale-105">
      <span
        className="text-dark-primary font-bold text-xl font-sans"
        aria-hidden="true"
      >
        F
      </span>
    </div>
    <div className={`${wordmarkClassName} flex-col leading-tight`}>
      <span className="text-lg font-bold text-dark-primary font-sans tracking-tight">
        FundFlow AI
      </span>
      <span className="text-[10px] font-semibold text-gray-700 tracking-wide">
        Autonomous Career Intelligence
      </span>
    </div>
  </Link>
)

export default Brand
