export const AREAS = ['home', 'forecast', 'fixes', 'planning', 'try', 'control', 'surrogate'] as const
export type Area = (typeof AREAS)[number]
