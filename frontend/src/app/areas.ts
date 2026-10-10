export const AREAS = ['home', 'forecast', 'fixes', 'planning', 'try', 'proof'] as const
export type Area = (typeof AREAS)[number]
