import React from 'react'
import SidebarNav from './SidebarNav'

/**
 * Desktop section navigation. Hidden below the `md` breakpoint (768px),
 * where `MobileNav` renders the same links in a drawer instead.
 *
 * The link list lives in `SidebarNav` so both surfaces share one definition.
 */
const Sidebar = () => (
  <aside
    className="fixed left-0 top-16 bottom-0 w-64 bg-background-secondary/40 backdrop-blur-sm border-r border-border-light hidden md:block"
    aria-label="Section navigation"
  >
    <SidebarNav />
  </aside>
)

export default Sidebar
