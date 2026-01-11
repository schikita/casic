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
          className="rounded-xl px-3 py-2 bg-zinc-100 text-black active:bg-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
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
          className="rounded-xl px-3 py-2 bg-zinc-100 text-black active:bg-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
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
            className="bg-white w-full rounded-t-2xl p-4 pb-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div id="menu-title" className="text-lg font-bold text-black mb-2">Меню</div>

            <div className="grid gap-2">
              <button
                className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-400"
                onClick={() => go("/")}
              >
                Стол
              </button>

              {canAccessAdmin && (
                <>
                  <div className="text-xs text-zinc-400 mt-2 font-medium">Админка</div>
                  {isSuperadmin && (
                    <button
                      className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-400"
                      onClick={() => go("/admin?tab=tables")}
                    >
                      Админ: Столы
                    </button>
                  )}
                  <button
                    className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-400"
                    onClick={() => go("/admin?tab=users")}
                  >
                    Админ: Пользователи
                  </button>
                  {isSuperadmin && (
                    <button
                      className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-400"
                      onClick={() => go("/admin?tab=purchases")}
                    >
                      Админ: Покупки
                    </button>
                  )}
                  <button
                    className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-400"
                    onClick={() => go("/admin/export")}
                  >
                    Админ: Выгрузка
                  </button>
                  <button
                    className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-400"
                    onClick={() => go("/admin/sessions")}
                  >
                    Админ: Сессии
                  </button>
                  <button
                    className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-400"
                    onClick={() => go("/admin/summary")}
                  >
                    Админ: Итоги дня
                  </button>
                  <button
                    className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-400"
                    onClick={() => go("/admin/balance-adjustments")}
                  >
                    Админ: Баланс
                  </button>
                  <button
                    className="rounded-xl bg-zinc-100 px-4 py-3 text-left text-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-400"
                    onClick={() => go("/admin/report")}
                  >
                    Админ: Отчёт XLSX
                  </button>
                </>
              )}

              <button
                className="rounded-xl bg-white border px-4 py-3 text-left text-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-400"
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
