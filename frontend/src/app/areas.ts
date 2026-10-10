export const AREAS = ['home', 'forecast', 'fixes', 'planning', 'try'] as const
export type Area = (typeof AREAS)[number]
