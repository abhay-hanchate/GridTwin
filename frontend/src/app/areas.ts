export const AREAS = ['home', 'forecast', 'fixes', 'planning', 'try', 'control'] as const
export type Area = (typeof AREAS)[number]
