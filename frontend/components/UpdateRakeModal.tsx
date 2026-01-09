"use client";

import { useState, useEffect } from "react";
import { apiJson } from "@/lib/api";

type Props = {
  open: boolean;
  sessionId: string;
  currentRakeOut: number;
  onClose: () => void;
  onUpdated: () => void;
};

export default function UpdateRakeModal({
  open,
  sessionId,
  currentRakeOut,
  onClose,
  onUpdated,
}: Props) {
  const [rakeOut, setRakeOut] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setRakeOut(String(currentRakeOut));
      setError(null);
    }
  }, [open, currentRakeOut]);

  async function handleSubmit() {
    const value = rakeOut.trim() ? parseInt(rakeOut.trim(), 10) : 0;
    if (isNaN(value) || value < 0) {
      setError("Рейк должен быть неотрицательным числом");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await apiJson(`/api/sessions/${sessionId}/rake?rake_out=${value}`, {
        method: "POST",
      });
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка обновления рейка");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

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
          <div className="text-lg font-bold text-black">Обновить рейк при выходе</div>
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

        <div className="mb-6">
          <label className="block text-sm font-medium text-zinc-700 mb-2">
            Рейк при выходе
          </label>
          <input
            type="number"
            className="w-full rounded-xl border px-3 py-3 text-base text-black bg-white"
            placeholder="0"
            value={rakeOut}
            onChange={(e) => setRakeOut(e.target.value)}
            disabled={submitting}
            min="0"
            step="1"
            autoFocus
          />
          <p className="text-xs text-zinc-500 mt-1">
            Количество фишек, которое дилер уносит со стола
          </p>
        </div>

        <button
          className="w-full rounded-xl bg-blue-600 text-white py-4 font-bold text-lg active:bg-blue-700 disabled:opacity-60"
          onClick={handleSubmit}
          disabled={submitting}
        >
          {submitting ? "Сохранение..." : "Сохранить"}
        </button>
      </div>
    </div>
  );
}

