"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import type { Staff } from "@/lib/types";

type Props = {
  open: boolean;
  sessionId: string;
  currentDealerId: number | null;
  onClose: () => void;
  onDealerReplaced: () => void;
};

export default function ReplaceDealerModal({
  open,
  sessionId,
  currentDealerId,
  onClose,
  onDealerReplaced,
}: Props) {
  const [dealers, setDealers] = useState<Staff[]>([]);
  const [selectedDealerId, setSelectedDealerId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDealers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch("/api/sessions/available-dealers");
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка загрузки дилеров");
      }
      const data = await res.json();
      // Filter out the current dealer
      const available = data.filter((d: Staff) => d.id !== currentDealerId);
      setDealers(available);
      if (available.length > 0) {
        setSelectedDealerId(available[0].id);
      }
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, [currentDealerId]);

  useEffect(() => {
    if (open) {
      loadDealers();
    }
  }, [open, loadDealers]);

  const handleSubmit = async () => {
    if (!selectedDealerId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/sessions/${sessionId}/replace-dealer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_dealer_id: selectedDealerId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка замены дилера");
      }
      onDealerReplaced();
      onClose();
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка");
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-end"
      onClick={onClose}
    >
      <div
        className="bg-white w-full rounded-t-2xl p-4 pb-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-lg font-bold text-black mb-3">Заменить дилера</div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-100 text-red-700 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-zinc-500 text-sm mb-3">Загрузка доступных дилеров…</div>
        ) : dealers.length === 0 ? (
          <div className="text-zinc-500 text-sm mb-3">Нет доступных дилеров для замены</div>
        ) : (
          <div className="mb-4">
            <label className="block text-sm text-zinc-600 mb-1">Выберите нового дилера</label>
            <select
              className="w-full rounded-xl border border-zinc-300 bg-white text-black px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-zinc-400"
              value={selectedDealerId ?? ""}
              onChange={(e) => setSelectedDealerId(Number(e.target.value))}
              disabled={submitting}
            >
              {dealers.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.username}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          <button
            className="rounded-xl bg-zinc-100 px-4 py-3 text-zinc-700 active:bg-zinc-200"
            onClick={onClose}
            disabled={submitting}
          >
            Отмена
          </button>
          <button
            className="rounded-xl bg-blue-600 text-white px-4 py-3 active:bg-blue-700 disabled:opacity-50"
            onClick={handleSubmit}
            disabled={submitting || loading || dealers.length === 0}
          >
            {submitting ? "Замена…" : "Заменить"}
          </button>
        </div>
      </div>
    </div>
  );
}

