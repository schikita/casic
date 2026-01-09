"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/AuthContext";

export default function TopMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const router = useRouter();

  const canSuperadmin = useMemo(() => user?.role === "superadmin", [user]);
  const canExport = useMemo(
    () => user?.role === "superadmin" || user?.role === "table_admin",
    [user]
  );

  function go(path: string) {
    setOpen(false);
    router.push(path);
  }

  return (
    <>
      <div className="flex items-center justify-between mb-3">
        <button
          className="rounded-xl px-3 py-2 bg-zinc-100 text-black active:bg-zinc-200 text-sm"
          onClick={() => setOpen(true)}
        >
          Меню
        </button>

        <div className="text-xs text-zinc-500">
          {user ? user.username + " (" + user.role + ")" : ""}
        </div>
      </div>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/40 flex items-end"
          onClick={() => setOpen(false)}
        >
          <div
            className="bg-white w-full rounded-t-2xl p-4 pb-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-lg font-bold text-black mb-2">Меню</div>

            <div className="grid gap-2">
              <button
                className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-gray-400"
                onClick={() => go("/")}
              >
                Стол
              </button>

              {canSuperadmin && (
                <button
                  className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-gray-400"
                  onClick={() => go("/admin")}
                >
                  Админка
                </button>
              )}

              {canExport && (
                <button
                  className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-gray-400"
                  onClick={() => go("/admin/export")}
                >
                  Выгрузка (CSV/TSV)
                </button>
              )}

              {canExport && (
                <button
                  className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-gray-400"
                  onClick={() => go("/admin/sessions")}
                >
                  История сессий
                </button>
              )}

              {canSuperadmin && (
                <button
                  className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-gray-400"
                  onClick={() => go("/admin/summary")}
                >
                  Итоги дня
                </button>
              )}

              {canSuperadmin && (
                <button
                  className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-gray-400"
                  onClick={() => go("/admin/balance-adjustments")}
                >
                  Корректировки баланса
                </button>
              )}

              {canSuperadmin && (
                <button
                  className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-gray-400"
                  onClick={() => go("/admin/report")}
                >
                  Отчёт дня (XLSX)
                </button>
              )}

              <button
                className="rounded-xl bg-zinc-900 text-white px-4 py-3 text-left"
                onClick={() => {
                  logout();
                  go("/login");
                }}
              >
                Выйти
              </button>

              <button
                className="rounded-xl bg-white border px-4 py-3 text-left text-gray-400"
                onClick={() => setOpen(false)}
              >
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
