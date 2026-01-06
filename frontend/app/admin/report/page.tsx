"use client";

import { useState } from "react";
import TopMenu from "@/components/TopMenu";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import { apiDownload } from "@/lib/api";

function todayLocalISO() {
  const d = new Date();
  const yyyy = String(d.getFullYear());
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function ReportPage() {
  const { user } = useAuth();

  const [date, setDate] = useState(todayLocalISO());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

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
    } catch (e: any) {
      setError(e?.message ?? "Ошибка генерации отчёта");
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

  if (user.role !== "superadmin") {
    return (
      <RequireAuth>
        <main className="p-4 max-w-md mx-auto">
          <TopMenu />
          <div className="mt-4 rounded-xl bg-zinc-900 text-white px-4 py-3">
            Доступ запрещён. Только для суперадмина.
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
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-50 text-red-700 px-3 py-2 text-sm">
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
                className="w-full rounded-xl border px-3 py-3 text-base text-black"
                disabled={busy}
              />
            </div>

            <button
              className="rounded-xl bg-green-600 text-white px-4 py-3 font-semibold disabled:opacity-60"
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

