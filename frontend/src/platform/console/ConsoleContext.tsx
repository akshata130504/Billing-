import { createContext, useContext } from 'react';
import type { PlatformMe, PlatformRole } from '../platformApi';

export interface ConsoleSession {
  me: PlatformMe;
  role: PlatformRole;
  /** UI convenience only: every permission is enforced by the server. */
  hasRole: (...roles: PlatformRole[]) => boolean;
  signOut: () => Promise<void>;
}

export const ConsoleContext = createContext<ConsoleSession | null>(null);

export function useConsole(): ConsoleSession {
  const value = useContext(ConsoleContext);
  if (!value) throw new Error('useConsole must be used inside the platform console layout');
  return value;
}

export const ADMIN: PlatformRole = 'platform_administrator';
export const OPS: PlatformRole = 'platform_operations';
