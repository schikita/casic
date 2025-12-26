"use client";

import { createContext, useContext } from "react";
import type { User } from "@/lib/types";

export type AuthState = {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<User>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthContext is not mounted");
  return ctx;
}

export default AuthContext;
