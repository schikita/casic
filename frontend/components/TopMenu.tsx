"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/AuthContext";

export default function TopMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const router = useRouter();

  const canAccessAdmin = useMemo(() => user?.role === "superadmin" || user?.role === "table_admin", [user]);
  const isSuperadmin = useMemo(() => user?.role === "superadmin", [user]);

  function go(path: string) {
    setOpen(false);
    router.push(path);
  }

  return (
    <>
      <div className="flex items-center justify-between mb-3">
        <button
          className="rounded-xl px-3 py-2 bg-zinc-800 text-white active:bg-zinc-700 text-sm focus:outline-none border border-zinc-700"
          onClick={() => setOpen(true)}
          aria-expanded={open}
          aria-controls="menu-dropdown"
        >
          Меню
        </button>

        <div className="text-white font-semibold">
          {user ? user.username : ""}
        </div>

        <button
          className="rounded-xl px-3 py-2 bg-zinc-800 text-white active:bg-zinc-700 text-sm focus:outline-none border border-zinc-700"
          onClick={() => {
            logout();
            router.push("/login");
          }}
          aria-label="Выйти"
          title="Выйти"
        >
          Выход
        </button>
      </div>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/40 flex items-end"
          onClick={() => setOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="menu-title"
        >
          <div
            className="bg-zinc-900 w-full rounded-t-2xl p-4 pb-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div id="menu-title" className="text-lg font-bold text-white mb-2">Меню</div>

            <div className="grid gap-2">
              {!isSuperadmin && (
                <button
                  className="rounded-xl bg-zinc-800 px-4 py-3 text-left text-zinc-300 focus:outline-none border border-zinc-700 active:bg-zinc-700"
                  onClick={() => go("/")}
                >
                  Игра
                </button>
              )}

              {isSuperadmin && (
                <button
                  className="rounded-xl bg-zinc-800 px-4 py-3 text-left text-zinc-300 focus:outline-none border border-zinc-700 active:bg-zinc-700"
                  onClick={() => go("/admin?tab=users")}
                >
                  Пользователи
                </button>
              )}

              {canAccessAdmin && !isSuperadmin && (
                <>
                  <button
                    className="rounded-xl bg-zinc-800 px-4 py-3 text-left text-zinc-300 focus:outline-none border border-zinc-700 active:bg-zinc-700"
                    onClick={() => go("/admin?tab=tables")}
                  >
                    Столы
                  </button>
                  <button
                    className="rounded-xl bg-zinc-800 px-4 py-3 text-left text-zinc-300 focus:outline-none border border-zinc-700 active:bg-zinc-700"
                    onClick={() => go("/admin?tab=users")}
                  >
                    Персонал
                  </button>
                  <button
                    className="rounded-xl bg-zinc-800 px-4 py-3 text-left text-zinc-300 focus:outline-none border border-zinc-700 active:bg-zinc-700"
                    onClick={() => go("/admin/sessions")}
                  >
                    Сессии
                  </button>
                  <button
                    className="rounded-xl bg-zinc-800 px-4 py-3 text-left text-zinc-300 focus:outline-none border border-zinc-700 active:bg-zinc-700"
                    onClick={() => go("/admin/summary")}
                  >
                    Итоги дня
                  </button>
                  <button
                    className="rounded-xl bg-zinc-800 px-4 py-3 text-left text-zinc-300 focus:outline-none border border-zinc-700 active:bg-zinc-700"
                    onClick={() => go("/admin/balance-adjustments")}
                  >
                    Расходы
                  </button>
                  <button
                    className="rounded-xl bg-zinc-800 px-4 py-3 text-left text-zinc-300 focus:outline-none border border-zinc-700 active:bg-zinc-700"
                    onClick={() => go("/admin/report")}
                  >
                    Отчёт XLSX
                  </button>
                </>
              )}

              <button
                className="rounded-xl bg-zinc-800 border border-zinc-600 px-4 py-3 text-left text-zinc-400 focus:outline-none active:bg-zinc-700"
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
