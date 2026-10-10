export const AREAS = ['home', 'forecast', 'fixes', 'planning', 'try', 'proof', 'control'] as const
export type Area = (typeof AREAS)[number]
