import type { Api } from './api';
import { createHttpApi } from './http';
import { createMockApi } from './mock';

// Empty VITE_API_BASE_URL means "use the built-in sample data". Set it to talk to the FastAPI backend.
const base = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();

export const api: Api = base ? createHttpApi(base) : createMockApi({ latencyMs: [180, 420] });
export const isDemo = api.mode === 'mock';
export type { Api };
