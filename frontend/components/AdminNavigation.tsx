"use client";

import { useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "./auth/AuthContext";

interface AdminNavigationProps {
  activeTab?: "tables" | "users" | "purchases";
}

export default function AdminNavigation({ activeTab }: AdminNavigationProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { user } = useAuth();
  const [showMenu, setShowMenu] = useState(false);
  
  // Determine if current user is table_admin
  const isTableAdmin = user?.role === "table_admin";

  return (
    <>
      {/* Toggle button */}
      <button
        className="rounded-xl bg-zinc-800 text-white px-3 py-2 text-sm disabled:opacity-60 hover:bg-zinc-700/90"
        onClick={() => setShowMenu(!showMenu)}
        aria-expanded={showMenu}
        aria-controls="admin-navigation-menu"
        aria-label="Открыть меню админки"
      >
        {showMenu ? "☰" : "☰"}
      </button>

      {/* Compact navigation for all admin pages */}
      {showMenu && (
        <div
          className="fixed inset-0 z-40 bg-black/40 flex items-end"
          onClick={() => setShowMenu(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="admin-nav-title"
        >
          <div
            className="bg-zinc-900 w-full rounded-t-2xl p-4 pb-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div id="admin-nav-title" className="text-lg font-bold text-white mb-3">Админка</div>
            <div className="text-xs text-zinc-400 mb-3 font-medium">Разделы</div>
            <div className="grid grid-cols-2 gap-2">
              {/* Tables tab - only for superadmin */}
              {!isTableAdmin && (
                <button
                  className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                    pathname === "/admin" && activeTab === "tables"
                      ? "bg-zinc-700 text-white"
                      : "bg-black text-zinc-300 hover:bg-zinc-800 hover:text-white"
                  }`}
                  onClick={() => {
                    router.push("/admin?tab=tables");
                    setShowMenu(false);
                  }}
                  aria-current={pathname === "/admin" && activeTab === "tables" ? "page" : undefined}
                >
                  Столы
                </button>
              )}

              <button
                className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                  pathname === "/admin" && activeTab === "users"
                    ? "bg-zinc-700 text-white"
                    : "bg-black text-zinc-300 hover:bg-zinc-800 hover:text-white"
                }`}
                onClick={() => {
                  router.push("/admin?tab=users");
                  setShowMenu(false);
                }}
              >
                Пользователи
              </button>

              {/* Purchases tab - only for superadmin */}
              {!isTableAdmin && (
                <button
                  className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                    pathname === "/admin" && activeTab === "purchases"
                      ? "bg-zinc-700 text-white"
                      : "bg-black text-zinc-300 hover:bg-zinc-800 hover:text-white"
                  }`}
                  onClick={() => {
                    router.push("/admin?tab=purchases");
                    setShowMenu(false);
                  }}
                >
                  Покупки
                </button>
              )}

              <button
                className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                  pathname === "/admin/export"
                    ? "bg-zinc-700 text-white"
                    : "bg-black text-zinc-300 hover:bg-zinc-800 hover:text-white"
                }`}
                onClick={() => {
                  router.push("/admin/export");
                  setShowMenu(false);
                }}
              >
                Выгрузка
              </button>

              <button
                className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                  pathname === "/admin/sessions"
                    ? "bg-zinc-700 text-white"
                    : "bg-black text-zinc-300 hover:bg-zinc-800 hover:text-white"
                }`}
                onClick={() => {
                  router.push("/admin/sessions");
                  setShowMenu(false);
                }}
              >
                Сессии
              </button>

              <button
                className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                  pathname === "/admin/summary"
                    ? "bg-zinc-700 text-white"
                    : "bg-black text-zinc-300 hover:bg-zinc-800 hover:text-white"
                }`}
                onClick={() => {
                  router.push("/admin/summary");
                  setShowMenu(false);
                }}
              >
                Итоги дня
              </button>

              {/* Balance adjustments tab - only for superadmin */}
              {!isTableAdmin && (
                <button
                  className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                    pathname === "/admin/balance-adjustments"
                      ? "bg-zinc-700 text-white"
                      : "bg-black text-zinc-300 hover:bg-zinc-800 hover:text-white"
                  }`}
                  onClick={() => {
                    router.push("/admin/balance-adjustments");
                    setShowMenu(false);
                  }}
                >
                  Баланс
                </button>
              )}

              <button
                className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                  pathname === "/admin/report"
                    ? "bg-zinc-700 text-white"
                    : "bg-black text-zinc-300 hover:bg-zinc-800 hover:text-white"
                }`}
                onClick={() => {
                  router.push("/admin/report");
                  setShowMenu(false);
                }}
              >
                Отчёт XLSX
              </button>
            </div>

            <button
              className="mt-4 w-full rounded-xl bg-white border px-4 py-3 text-left text-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              onClick={() => setShowMenu(false)}
            >
              Закрыть
            </button>
          </div>
        </div>
      )}
    </>
  );
}
