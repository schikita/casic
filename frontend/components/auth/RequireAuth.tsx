"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "./AuthContext";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;
    if (!user && pathname !== "/login") {
      router.replace("/login");
    }
  }, [user, loading, router, pathname]);

  if (pathname === "/login") return <>{children}</>;
  if (loading)
    return <div className="p-4 text-sm text-zinc-600">Загрузка…</div>;
  if (!user) return null;

  return <>{children}</>;
}
