import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import Brand from './Brand'
import SidebarNav from './SidebarNav'

/**
 * Mobile navigation: hamburger trigger plus slide-in drawer.
 *
 * Only rendered below the `md` breakpoint (768px) — the desktop sidebar owns
 * navigation at or above it, and is untouched by this component.
 *
 * The drawer's contents are the shared `SidebarNav` and `Brand` components,
 * so items, icons, active highlighting, branding and routing behaviour are
 * identical to the desktop sidebar with no duplicated logic.
 */

/**
 * Exit-animation length. Must stay in sync with the `duration-300` utility on
 * the backdrop and panel below: the panel stays mounted this long after close
 * so its slide-out can play before React removes it.
 *
 * Under `prefers-reduced-motion` the global rule in index.css collapses the
 * CSS transition to ~0ms; this timer still runs, which only means the drawer
 * unmounts a beat later. Nothing visual depends on it.
 */
const TRANSITION_MS = 300

/** Tabbable elements inside the panel, in DOM order, for the focus trap. */
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'

const MobileNav = () => {
  // Two pieces of state drive the animation: `isMounted` controls presence in
  // the DOM, `isShown` controls the transform/opacity. Opening mounts first
  // and animates on the next frame; closing animates first and unmounts after.
  const [isMounted, setIsMounted] = useState(false)
  const [isShown, setIsShown] = useState(false)

  const panelRef = useRef(null)
  const triggerRef = useRef(null)
  const unmountTimer = useRef(null)
  // Mirrors the logical open state for callbacks that must not depend on
  // (and re-subscribe to) render state.
  const isOpenRef = useRef(false)
  const location = useLocation()
  const lastPathname = useRef(location.pathname)

  const open = useCallback(() => {
    if (isOpenRef.current) return
    isOpenRef.current = true
    clearTimeout(unmountTimer.current)
    setIsMounted(true)
  }, [])

  const close = useCallback(() => {
    // Guard so a stray call (e.g. the route-change effect below) cannot
    // steal focus back to the trigger while the drawer is already closed.
    if (!isOpenRef.current) return
    isOpenRef.current = false
    setIsShown(false)
    clearTimeout(unmountTimer.current)
    unmountTimer.current = setTimeout(() => {
      setIsMounted(false)
      // Return focus to the control that opened the drawer.
      triggerRef.current?.focus()
    }, TRANSITION_MS)
  }, [])

  // Animate in on the frame after mount, so the browser has a chance to paint
  // the closed position first and the transition actually runs.
  useEffect(() => {
    if (!isMounted) return undefined
    const frame = requestAnimationFrame(() => setIsShown(true))
    return () => cancelAnimationFrame(frame)
  }, [isMounted])

  // Move focus into the drawer once it is open.
  useEffect(() => {
    if (!isShown) return
    panelRef.current?.querySelector(FOCUSABLE_SELECTOR)?.focus()
  }, [isShown])

  // Escape to close, and keep Tab cycling inside the panel while open.
  useEffect(() => {
    if (!isMounted) return undefined

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        close()
        return
      }
      if (event.key !== 'Tab') return

      const focusable = panelRef.current?.querySelectorAll(FOCUSABLE_SELECTOR)
      if (!focusable || focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [isMounted, close])

  // Stop the page behind the drawer from scrolling.
  useEffect(() => {
    if (!isMounted) return undefined
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [isMounted])

  // Close on browser back/forward. Link clicks are already handled by the
  // `onNavigate` callbacks; this covers history changes that bypass them.
  // Comparing against the previous pathname keeps opening the drawer (which
  // does not change the route) from immediately closing it.
  useEffect(() => {
    if (lastPathname.current === location.pathname) return
    lastPathname.current = location.pathname
    close()
  }, [location.pathname, close])

  // If the viewport grows past the breakpoint the desktop sidebar takes over,
  // so drop the drawer rather than leaving it open behind the layout.
  useEffect(() => {
    if (!isMounted) return undefined
    const query = window.matchMedia('(min-width: 768px)')
    const onChange = (event) => {
      if (event.matches) close()
    }
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [isMounted, close])

  // Never leave a timer running after unmount.
  useEffect(() => () => clearTimeout(unmountTimer.current), [])

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={open}
        className="md:hidden -ml-1 mr-1 inline-flex items-center justify-center rounded-pipeup p-2 text-dark-primary transition-all duration-pipeup hover:bg-background-secondary"
        aria-label="Open navigation menu"
        aria-haspopup="dialog"
        aria-expanded={isShown}
        aria-controls="mobile-nav-drawer"
      >
        <Menu className="w-5 h-5" aria-hidden="true" />
      </button>

      {isMounted && (
        <div className="md:hidden">
          {/* Backdrop. Clicking anywhere outside the panel closes the drawer. */}
          <div
            onClick={close}
            className={`fixed inset-0 z-[60] bg-dark-primary/40 backdrop-blur-sm transition-opacity duration-300 ease-pipeup ${
              isShown ? 'opacity-100' : 'opacity-0'
            }`}
            aria-hidden="true"
          />

          <div
            ref={panelRef}
            id="mobile-nav-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Site navigation"
            className={`fixed left-0 top-0 bottom-0 z-[70] flex w-64 max-w-[80vw] flex-col overflow-y-auto border-r border-border-light bg-background-card shadow-pipeup-xl transition-transform duration-300 ease-pipeup ${
              isShown ? 'translate-x-0' : '-translate-x-full'
            }`}
          >
            <div className="flex items-center justify-between gap-3 border-b border-border-light px-5 py-3">
              <Brand wordmarkClassName="flex" onNavigate={close} />
              <button
                type="button"
                onClick={close}
                className="inline-flex items-center justify-center rounded-pipeup p-2 text-dark-primary transition-all duration-pipeup hover:bg-background-secondary"
                aria-label="Close navigation menu"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            <SidebarNav onNavigate={close} />
          </div>
        </div>
      )}
    </>
  )
}

export default MobileNav
