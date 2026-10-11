export const AREAS = ['home', 'forecast', 'fixes', 'planning', 'try', 'control', 'surrogate', 'evidence'] as const
export type Area = (typeof AREAS)[number]
