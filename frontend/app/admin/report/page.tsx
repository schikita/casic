"use client";

import { useState, useEffect } from "react";
import TopMenu from "@/components/TopMenu";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import { apiDownload, apiFetch } from "@/lib/api";

function todayLocalISO() {
  const d = new Date();
  const yyyy = String(d.getFullYear());
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

async function fetchPreselectedDate(): Promise<string> {
  const res = await apiFetch("/api/admin/day-summary/preselected-date");
  if (!res.ok) {
    throw new Error("Failed to fetch preselected date");
  }
  const data = await res.json();
  return data.date;
}

export default function ReportPage() {
  const { user } = useAuth();
  
  const [date, setDate] = useState(todayLocalISO());
  const [initialDateLoaded, setInitialDateLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  // Load preselected date on mount (same logic as summary page)
  useEffect(() => {
    if ((user?.role === "superadmin" || user?.role === "table_admin") && !initialDateLoaded) {
      fetchPreselectedDate()
        .then((preselectedDate) => {
          setDate(preselectedDate);
          setInitialDateLoaded(true);
        })
        .catch(() => {
          // Fallback to today if preselected date fetch fails
          setInitialDateLoaded(true);
        });
    }
  }, [user, initialDateLoaded]);

  async function downloadReport() {
    setError(null);
    setOk(null);

    if (!user) return;

    if (!date) {
      setError("Выберите дату");
      return;
    }

    setBusy(true);
    try {
      const qs = new URLSearchParams({ date });
      const path = "/api/admin/export-report?" + qs.toString();
      const filename = `casino_report_${date}.xlsx`;

      await apiDownload(path, filename);

      setOk("Отчёт скачан");
      setTimeout(() => setOk(null), 2500);
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка генерации отчёта");
    } finally {
      setBusy(false);
    }
  }

  if (!user) {
    return (
      <RequireAuth>
        <div className="p-4 text-white">Загрузка…</div>
      </RequireAuth>
    );
  }

  if (user.role !== "superadmin" && user.role !== "table_admin") {
    return (
      <RequireAuth>
        <main className="p-4 max-w-md mx-auto">
          <TopMenu />
          <div className="mt-4 rounded-xl bg-zinc-900 text-white px-4 py-3">
            Доступ запрещён. Только для суперадмина или администратора стола.
          </div>
        </main>
      </RequireAuth>
    );
  }

  return (
    <RequireAuth>
      <main className="p-3 max-w-md mx-auto">
        <TopMenu />

        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-xl font-bold text-white">Отчёт дня</div>
            <div className="text-xs text-zinc-400">
              Комплексный отчёт по всем столам
            </div>
          </div>
          <button
            className="rounded-xl bg-black text-white px-3 py-2 text-sm disabled:opacity-60 hover:bg-zinc-800/90"
            onClick={() => {
              setError(null);
              setOk(null);
            }}
            disabled={busy}
          >
            Обновить
          </button>
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-900/50 text-red-200 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {ok && (
          <div className="mb-3 rounded-xl bg-green-50 text-green-800 px-3 py-2 text-sm">
            {ok}
          </div>
        )}

        <div className="rounded-xl bg-zinc-900 p-4">
          <div className="grid gap-3">
            <div>
              <div className="text-xs text-zinc-400 mb-1">Дата отчёта</div>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-white/15 placeholder-zinc-500"
                disabled={busy}
              />
            </div>

            <button
              className="rounded-xl bg-green-600 text-white px-4 py-3 font-semibold disabled:opacity-60 hover:bg-green-700/90"
              onClick={downloadReport}
              disabled={busy || !date}
            >
              Скачать отчёт (XLSX)
            </button>

            <div className="text-xs text-zinc-400">
              Отчёт включает:
              <ul className="mt-1 ml-4 list-disc">
                <li>Состояние столов (места, игроки, фишки)</li>
                <li>Хронология покупок фишек</li>
                <li>Зарплаты персонала</li>
                <li>Корректировки баланса</li>
                <li>Итоги дня (прибыль/расходы)</li>
              </ul>
            </div>
          </div>
        </div>

        {busy && (
          <div className="fixed bottom-4 left-0 right-0 flex justify-center pointer-events-none">
            <div className="rounded-xl bg-black/80 text-white px-4 py-2 text-sm">
              Генерация отчёта…
            </div>
          </div>
        )}
      </main>
    </RequireAuth>
  );
}

