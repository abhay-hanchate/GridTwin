/** A gate's measured value as results.json holds it: a sentence, a number, a list, or named values (nested). Values
 *  are shown exactly as stored, never rounded, so every number on the Proof page is one that results.json contains. */
export default function Measured({ value }: { value: unknown }) {
  if (value === null || value === undefined) return null
  if (Array.isArray(value)) return <>{value.map(String).join(', ')}</>
  if (typeof value === 'object') {
    return (
      <dl className="measured">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k}><dt>{k.replace(/_/g, ' ')}</dt><dd><Measured value={v} /></dd></div>
        ))}
      </dl>
    )
  }
  return <>{String(value)}</>
}
