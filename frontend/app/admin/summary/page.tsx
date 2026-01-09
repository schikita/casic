"use client";

import { useState, useEffect } from "react";
import TopMenu from "@/components/TopMenu";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import { apiFetch } from "@/lib/api";

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

interface StaffEntry {
  name: string;
  role: string;
  hours: number;
  hourly_rate: number;
  salary: number;
}

interface SummaryData {
  date: string;
  income: { buyin_cash: number };
  expenses: { salaries: number; buyin_credit: number };
  result: number;
  info: { player_balance: number; total_sessions: number; open_sessions: number };
  staff: StaffEntry[];
}

function formatMoney(n: number | undefined | null) {
  if (n === undefined || n === null) {
    return "0";
  }
  return n.toLocaleString("ru-RU");
}

export default function SummaryPage() {
  const { user } = useAuth();
  const [date, setDate] = useState(todayLocalISO());
  const [data, setData] = useState<SummaryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [initialDateLoaded, setInitialDateLoaded] = useState(false);

  async function loadSummary(d: string) {
    if (!d) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/admin/day-summary?date=${d}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка загрузки");
      }
      setData(await res.json());
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка");
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user?.role === "superadmin" && !initialDateLoaded) {
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

  useEffect(() => {
    if (user?.role === "superadmin" && date && initialDateLoaded) {
      loadSummary(date);
    }
  }, [user, date, initialDateLoaded]);

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

  const resultColor = data
    ? data.result >= 0
      ? "text-green-400"
      : "text-red-400"
    : "";

  return (
    <RequireAuth>
      <main className="p-3 max-w-md mx-auto pb-20">
        <TopMenu />

        <div className="flex items-center justify-between mb-3">
          <div className="text-xl font-bold text-white">Итоги дня</div>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="rounded-lg border px-2 py-1 text-sm"
            disabled={loading}
          />
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-900/50 text-red-200 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {loading && (
          <div className="text-center text-zinc-400 py-8">Загрузка...</div>
        )}

        {data && !loading && (
          <div className="space-y-3">
            {/* Result Card */}
            <div className="rounded-xl bg-zinc-900 p-4">
              <div className="text-xs text-zinc-500 mb-1">РЕЗУЛЬТАТ</div>
              <div className={`text-3xl font-bold ${resultColor}`}>
                {data.result >= 0 ? "+" : ""}
                {formatMoney(data.result)} ₪
              </div>
              <div className="text-xs text-zinc-500 mt-1">
                {data.result >= 0 ? "Прибыль" : "Убыток"} за {data.date}
              </div>
            </div>

            {/* Income */}
            <div className="rounded-xl bg-zinc-900 p-4">
              <div className="text-xs text-zinc-500 mb-2">ДОХОДЫ</div>
              <div className="flex justify-between items-center">
                <span className="text-zinc-300">Покупка фишек (наличные)</span>
                <span className="text-green-400 font-semibold">
                  +{formatMoney(data.income.buyin_cash)} ₪
                </span>
              </div>
            </div>

            {/* Expenses */}
            <div className="rounded-xl bg-zinc-900 p-4">
              <div className="text-xs text-zinc-500 mb-2">РАСХОДЫ</div>
              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-zinc-300">Зарплаты</span>
                  <span className="text-red-400 font-semibold">
                    -{formatMoney(data.expenses.salaries)} ₪
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-zinc-300">Покупка фишек (кредит)</span>
                  <span className="text-red-400 font-semibold">
                    -{formatMoney(data.expenses.buyin_credit)} ₪
                  </span>
                </div>
              </div>
            </div>

            {/* Info */}
            <div className="rounded-xl bg-zinc-900 p-4">
              <div className="text-xs text-zinc-500 mb-2">СПРАВОЧНО</div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-zinc-400">Баланс игроков</span>
                  <span className="text-zinc-300">
                    {formatMoney(data.info.player_balance)} ₪
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-zinc-400">Всего сессий</span>
                  <span className="text-zinc-300">{data.info.total_sessions}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-zinc-400">Открытых сессий</span>
                  <span className="text-zinc-300">{data.info.open_sessions}</span>
                </div>
              </div>
            </div>

            {/* Staff */}
            {data.staff.length > 0 && (
              <div className="rounded-xl bg-zinc-900 p-4">
                <div className="text-xs text-zinc-500 mb-2">ПЕРСОНАЛ</div>
                <div className="space-y-3">
                  {data.staff.map((s, i) => (
                    <div key={i} className="border-b border-zinc-800 pb-2 last:border-0 last:pb-0">
                      <div className="flex justify-between items-center">
                        <div>
                          <span className="text-zinc-200">{s.name}</span>
                          <span className="text-xs text-zinc-500 ml-2">
                            {s.role === "dealer" ? "дилер" : "официант"}
                          </span>
                        </div>
                        <span className="text-red-400 font-semibold">
                          -{formatMoney(s.salary)} ₪
                        </span>
                      </div>
                      <div className="text-xs text-zinc-500 mt-1">
                        {s.hours.toFixed(1)} ч × {formatMoney(s.hourly_rate)} ₪/ч
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </RequireAuth>
  );
}

