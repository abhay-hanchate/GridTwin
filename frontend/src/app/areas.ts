export const AREAS = ['home', 'forecast', 'fixes', 'planning', 'try', 'surrogate', 'proof'] as const
export type Area = (typeof AREAS)[number]
