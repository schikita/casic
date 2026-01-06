"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";
import type { Staff } from "@/lib/types";

type Props = {
  open: boolean;
  tableId: number;
  seatsCount: number;
  onClose: () => void;
  onSessionCreated: () => void;
};

export default function StartSessionModal({
  open,
  tableId,
  seatsCount,
  onClose,
  onSessionCreated,
}: Props) {
  const [dealers, setDealers] = useState<Staff[]>([]);
  const [waiters, setWaiters] = useState<Staff[]>([]);
  const [selectedDealer, setSelectedDealer] = useState<number | null>(null);
  const [selectedWaiter, setSelectedWaiter] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSelectedDealer(null);
    setSelectedWaiter(null);
    setError(null);
    loadStaff();
  }, [open]);

  async function loadStaff() {
    setLoading(true);
    setError(null);
    try {
      const [dealerList, waiterList] = await Promise.all([
        apiJson<Staff[]>("/api/sessions/available-dealers"),
        apiJson<Staff[]>("/api/sessions/available-waiters"),
      ]);
      setDealers(dealerList);
      setWaiters(waiterList);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit() {
    if (!selectedDealer) {
      setError("Необходимо выбрать дилера");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiJson("/api/sessions", {
        method: "POST",
        body: JSON.stringify({
          table_id: tableId,
          seats_count: seatsCount,
          dealer_id: selectedDealer,
          waiter_id: selectedWaiter,
        }),
      });
      onSessionCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка создания сессии");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  const canSubmit = selectedDealer !== null && !submitting && !loading;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      onClick={(e) => e.target === e.currentTarget && !submitting && onClose()}
    >
      <div
        className="bg-white w-full max-w-md rounded-2xl p-5 shadow-xl mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="text-lg font-bold text-black">Открыть сессию</div>
          <button
            className="text-zinc-600 px-3 py-2 disabled:opacity-50"
            onClick={onClose}
            disabled={submitting}
          >
            ✕
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-xl bg-red-50 text-red-700 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center py-6 text-zinc-600">Загрузка...</div>
        ) : (
          <>
            <div className="mb-4">
              <label className="block text-sm font-medium text-zinc-700 mb-2">
                Дилер <span className="text-red-500">*</span>
              </label>
              <select
                className="w-full rounded-xl border px-3 py-3 text-base text-black bg-white"
                value={selectedDealer ?? ""}
                onChange={(e) =>
                  setSelectedDealer(e.target.value ? Number(e.target.value) : null)
                }
                disabled={submitting}
              >
                <option value="">Выберите дилера</option>
                {dealers.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.username}
                  </option>
                ))}
              </select>
              {dealers.length === 0 && (
                <p className="text-xs text-zinc-500 mt-1">
                  Нет доступных дилеров
                </p>
              )}
            </div>

            <div className="mb-6">
              <label className="block text-sm font-medium text-zinc-700 mb-2">
                Официант <span className="text-zinc-400">(опционально)</span>
              </label>
              <select
                className="w-full rounded-xl border px-3 py-3 text-base text-black bg-white"
                value={selectedWaiter ?? ""}
                onChange={(e) =>
                  setSelectedWaiter(e.target.value ? Number(e.target.value) : null)
                }
                disabled={submitting}
              >
                <option value="">Без официанта</option>
                {waiters.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.username}
                  </option>
                ))}
              </select>
            </div>

            <button
              className="w-full rounded-xl bg-green-600 text-white py-4 font-bold text-lg active:bg-green-700 disabled:opacity-60"
              onClick={handleSubmit}
              disabled={!canSubmit}
            >
              {submitting ? "Создание..." : "Начать сессию"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

