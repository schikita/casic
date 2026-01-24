"use client";

import { useState, useEffect } from "react";
import TopMenu from "@/components/TopMenu";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import { apiFetch } from "@/lib/api";

interface BalanceAdjustment {
  id: number;
  created_at: string;
  amount: number;
  comment: string;
  created_by_username: string;
}

function formatMoney(n: number | undefined | null) {
  if (n === undefined || n === null) {
    return "0";
  }
  return n.toLocaleString("ru-RU");
}

function formatDateTime(isoString: string) {
  const d = new Date(isoString);
  const date = d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  const time = d.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${date} ${time}`;
}

export default function BalanceAdjustmentsPage() {
  const { user } = useAuth();
  const [adjustments, setAdjustments] = useState<BalanceAdjustment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  
  // Form state
  const [amount, setAmount] = useState("");
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function loadAdjustments() {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch("/api/admin/balance-adjustments?limit=50");
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка загрузки");
      }
      setAdjustments(await res.json());
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(isIncome: boolean) {
    if (!amount || !comment.trim()) {
      setError("Заполните все поля");
      return;
    }

    const amountValue = parseInt(amount, 10);
    if (isNaN(amountValue) || amountValue === 0) {
      setError("Сумма должна быть отличной от нуля");
      return;
    }

    // Apply sign based on isIncome parameter
    const finalAmount = isIncome ? amountValue : -amountValue;

    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch("/api/admin/balance-adjustments", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          amount: finalAmount,
          comment: comment.trim(),
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка сохранения");
      }

      // Reset form and reload
      setAmount("");
      setComment("");
      setShowAddForm(false);
      await loadAdjustments();
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка");
    } finally {
      setSubmitting(false);
    }
  }

  // Load adjustments on mount
  useEffect(() => {
    if (user?.role === "superadmin" || user?.role === "table_admin") {
      loadAdjustments();
    }
  }, [user]);

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
            Доступ запрещён. Только для администраторов.
          </div>
        </main>
      </RequireAuth>
    );
  }

  return (
    <RequireAuth>
      <main className="p-3 max-w-md mx-auto pb-20">
        <TopMenu />

        <div className="flex items-center justify-between mb-3">
          <div className="text-xl font-bold text-white">Корректировки баланса</div>
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-900/50 text-red-200 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {/* Add button */}
        {!showAddForm && (
          <button
            onClick={() => setShowAddForm(true)}
            className="w-full rounded-xl bg-green-600 text-white px-4 py-3 font-semibold mb-3 active:bg-green-700 disabled:opacity-60 hover:bg-green-700/90 focus:outline-none focus:ring-2 focus:ring-white/15"
          >
            + Добавить корректировку
          </button>
        )}

        {/* Add form */}
        {showAddForm && (
          <div className="rounded-xl bg-zinc-900 p-4 mb-3">
            <div className="text-white font-semibold mb-3">Новая корректировка</div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-zinc-400 mb-1">
                  Сумма
                </label>
                <input
                  type="number"
                  inputMode="numeric"
                  value={amount}
                  onChange={(e) => {
                    // Only allow positive numbers
                    const value = e.target.value;
                    if (value === "" || (/^\d+$/.test(value) && parseInt(value, 10) >= 0)) {
                      setAmount(value);
                    }
                  }}
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-white/15 placeholder-zinc-500"
                  placeholder="Например: 1000"
                  disabled={submitting}
                />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">
                  Комментарий
                </label>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  className="w-full rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-white/15 placeholder-zinc-500"
                  rows={3}
                  placeholder="Описание корректировки"
                  disabled={submitting}
                />
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => handleSubmit(true)}
                  disabled={submitting || !amount || !comment.trim()}
                  className="flex-1 rounded-xl bg-green-600 text-white px-4 py-3 font-semibold active:bg-green-700 disabled:opacity-50 hover:bg-green-700/90 focus:outline-none focus:ring-2 focus:ring-white/15"
                >
                  {submitting ? "..." : "Доход"}
                </button>
                <button
                  type="button"
                  onClick={() => handleSubmit(false)}
                  disabled={submitting || !amount || !comment.trim()}
                  className="flex-1 rounded-xl bg-red-600 text-white px-4 py-3 font-semibold active:bg-red-700 disabled:opacity-50 hover:bg-red-700/90 focus:outline-none focus:ring-2 focus:ring-white/15"
                >
                  {submitting ? "..." : "Расход"}
                </button>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowAddForm(false);
                  setAmount("");
                  setComment("");
                  setError(null);
                }}
                disabled={submitting}
                className="w-full rounded-xl bg-zinc-700 text-white px-4 py-2 font-semibold active:bg-zinc-600 disabled:opacity-50 hover:bg-zinc-600/90 focus:outline-none focus:ring-2 focus:ring-white/15"
              >
                Отмена
              </button>
            </div>
          </div>
        )}

        {/* List of adjustments */}
        <div className="space-y-2">
          {loading && (
            <div className="fixed bottom-4 left-0 right-0 flex justify-center pointer-events-none">
              <div className="rounded-xl bg-black/80 text-white px-4 py-2 text-sm">
                Загрузка…
              </div>
            </div>
          )}

          {!loading && adjustments.length === 0 && (
            <div className="rounded-xl bg-zinc-900 text-white/70 px-3 py-3 text-sm rounded-xl">
              Нет корректировок
            </div>
          )}

          {!loading && adjustments.map((adj) => (
            <div
              key={adj.id}
              className="rounded-xl bg-zinc-900 p-4"
            >
              <div className="flex justify-between items-start mb-2">
                <div className="flex-1">
                  <div className="text-xs text-zinc-400 mb-1">
                    {formatDateTime(adj.created_at)}
                  </div>
                  <div className="text-sm text-zinc-300">
                    {adj.comment}
                  </div>
                  <div className="text-xs text-zinc-400 mt-1">
                    {adj.created_by_username}
                  </div>
                </div>
                <div
                  className={`text-lg font-bold ${
                    adj.amount > 0 ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {adj.amount > 0 ? "+" : ""}
                  {formatMoney(adj.amount)} ₪
                </div>
              </div>
            </div>
          ))}
        </div>
      </main>
    </RequireAuth>
  );
}
