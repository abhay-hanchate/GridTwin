import { Info as InfoIcon } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

/** A long explanation behind a small (i): shown on hover, keyboard focus or tap, so pages stay short.
 *  The text stays in the page for screen readers and search. */
export default function Info({ children, label = 'More about this' }: { children: ReactNode; label?: string }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  return (
    <span className={`info ${open ? 'open' : ''}`}>
      <button type="button" className="info-btn" aria-label={label} aria-describedby={id} aria-expanded={open}
        onClick={() => setOpen((o) => !o)} onBlur={() => setOpen(false)}>
        <InfoIcon size={15} strokeWidth={2.2} aria-hidden="true" />
      </button>
      <span role="tooltip" id={id} className="info-pop">{children}</span>
    </span>
  )
}
