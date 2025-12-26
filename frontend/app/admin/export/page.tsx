"use client";

import { useEffect, useMemo, useState } from "react";
import TopMenu from "@/components/TopMenu";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import { apiDownload, apiJson } from "@/lib/api";

type Table = {
  id: number;
  name: string;
  seats_count: number;
};

function todayLocalISO() {
  const d = new Date();
  const yyyy = String(d.getFullYear());
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function AdminExportPage() {
  const { user } = useAuth();

  const [tables, setTables] = useState<Table[]>([]);
  const [date, setDate] = useState(todayLocalISO());
  const [format, setFormat] = useState<"tsv" | "csv">("csv");
  const [tableId, setTableId] = useState<string>("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const effectiveTableId = useMemo(() => {
    if (!user) return null;

    if (user.role === "superadmin") {
      const n = Number(tableId);
      return Number.isFinite(n) && n > 0 ? n : null;
    }

    return user.table_id ?? null;
  }, [user, tableId]);

  async function loadTablesIfNeeded() {
    if (!user) return;

    if (user.role !== "superadmin") {
      setTables([]);
      return;
    }

    const list = await apiJson<Table[]>("/api/admin/tables");
    setTables(list);

    if (!tableId && list.length > 0) {
      setTableId(String(list[0].id));
    }
  }

  useEffect(() => {
    if (!user) return;
    loadTablesIfNeeded().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  async function download() {
    setError(null);
    setOk(null);

    if (!user) return;

    if (!date) {
      setError("Выберите дату");
      return;
    }

    if (!effectiveTableId) {
      setError("Выберите стол");
      return;
    }

    setBusy(true);
    try {
      const qs = new URLSearchParams({
        date,
        format,
        table_id: String(effectiveTableId),
      });

      // Важно: здесь используем Next proxy-роут вашего приложения
      const path = "/api/admin/export?" + qs.toString();
      const filename = `session_table_${effectiveTableId}_${date}.${format}`;

      await apiDownload(path, filename);

      setOk("Файл скачан");
      setTimeout(() => setOk(null), 2500);
    } catch (e: any) {
      setError(e?.message ?? "Ошибка экспорта");
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
            Доступ запрещён
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
            <div className="text-xl font-bold text-white">Экспорт</div>
            <div className="text-xs text-zinc-400">
              Выгрузка отчёта по столу за выбранную дату
            </div>
          </div>

          <button
            className="rounded-xl bg-black text-white px-3 py-2 text-sm disabled:opacity-60"
            onClick={() => loadTablesIfNeeded()}
            disabled={busy}
          >
            Обновить
          </button>
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
              <div className="text-xs text-zinc-400 mb-1">Дата</div>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full rounded-xl border px-3 py-3 text-base text-black"
                disabled={busy}
              />
            </div>

            <div>
              <div className="text-xs text-zinc-400 mb-1">Формат</div>
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value as any)}
                className="w-full rounded-xl border px-3 py-3 text-base text-black"
                disabled={busy}
              >
                <option value="csv">CSV</option>
                <option value="tsv">TSV</option>
              </select>
            </div>

            {user.role === "superadmin" ? (
              <div>
                <div className="text-xs text-zinc-400 mb-1">Стол</div>
                <select
                  value={tableId}
                  onChange={(e) => setTableId(e.target.value)}
                  className="w-full rounded-xl border px-3 py-3 text-base text-black"
                  disabled={busy}
                >
                  {tables.length === 0 ? (
                    <option value="">Нет столов</option>
                  ) : (
                    tables.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name} (ID {t.id})
                      </option>
                    ))
                  )}
                </select>
              </div>
            ) : (
              <div className="rounded-xl bg-black text-white px-4 py-3">
                <div className="text-xs text-white/60">Стол</div>
                <div className="font-semibold">
                  {user.table_id ? `ID ${user.table_id}` : "—"}
                </div>
              </div>
            )}

            <button
              className="rounded-xl bg-green-600 text-white px-4 py-3 font-semibold disabled:opacity-60"
              onClick={download}
              disabled={busy || !date || !effectiveTableId}
            >
              Скачать
            </button>

            <div className="text-xs text-zinc-400">
              В файле: стол, дата, session_id, статус, место, игрок, итог фишек.
            </div>
          </div>
        </div>

        {busy && (
          <div className="fixed bottom-4 left-0 right-0 flex justify-center pointer-events-none">
            <div className="rounded-xl bg-black/80 text-white px-4 py-2 text-sm">
              Экспорт…
            </div>
          </div>
        )}
      </main>
    </RequireAuth>
  );
}
