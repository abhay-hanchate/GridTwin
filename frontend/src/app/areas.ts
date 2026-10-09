export const AREAS = ['home', 'try', 'fixes', 'planning', 'proof'] as const
export type Area = (typeof AREAS)[number]
