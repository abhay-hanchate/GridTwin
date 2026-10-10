import type { useT } from './i18n'

/** "Tomorrow" only when the day really is tomorrow; a precomputed demo day is named by its date. */
export function dayName(date: string, lang: string, t: ReturnType<typeof useT>): string {
  const tomorrow = new Date(Date.now() + 86_400_000).toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
  if (date === tomorrow) return t('home.tomorrow')
  return new Date(`${date}T12:00:00`).toLocaleDateString(lang === 'hi' ? 'hi-IN' : 'en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
}
