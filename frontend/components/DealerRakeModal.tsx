"use client";

import { useState, useEffect } from "react";
import { apiJson } from "@/lib/api";

type Props = {
  open: boolean;
  sessionId: string;
  assignmentId: number;
  dealerName: string;
  currentRake: number;
  onClose: () => void;
  onRakeUpdated: () => void;
};

export default function DealerRakeModal({
  open,
  sessionId,
  assignmentId,
  dealerName,
  currentRake,
  onClose,
  onRakeUpdated,
}: Props) {
  const [amount, setAmount] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setAmount("");
      setError(null);
    }
  }, [open]);

  const handleSubmit = async () => {
    const amountValue = parseInt(amount, 10);
    if (isNaN(amountValue) || amountValue <= 0) {
      setError("Введите сумму рейка (больше 0)");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await apiJson(`/api/sessions/${sessionId}/update-assignment-rake`, {
        method: "POST",
        body: JSON.stringify({
          assignment_id: assignmentId,
          amount: amountValue,
        }),
      });
      onRakeUpdated();
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
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) {
          onClose();
        }
      }}
    >
      <div
        className="bg-zinc-900 w-full max-w-md rounded-2xl p-5 shadow-xl mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="text-lg font-bold text-white">Добавить рейк</div>
          <button
            className="text-zinc-400 px-3 py-2 disabled:opacity-50 hover:text-white"
            onClick={onClose}
            disabled={submitting}
          >
            ✕
          </button>
        </div>

        <div className="mb-4 text-sm text-zinc-300">
          Дилер: <span className="font-semibold text-white">{dealerName}</span>
        </div>

        {currentRake > 0 && (
          <div className="mb-4 rounded-xl bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm text-zinc-300">
            Текущий рейк: <span className="font-semibold text-white">{currentRake} ₪</span>
          </div>
        )}

        {error && (
          <div className="mb-3 rounded-xl bg-red-900/50 text-red-200 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <div className="mb-4">
          <label className="block text-sm text-zinc-400 mb-1">
            Добавить рейк (₪)
          </label>
          <input
            type="number"
            inputMode="numeric"
            min="1"
            className="w-full rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-zinc-500 placeholder-zinc-500"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0"
            disabled={submitting}
            autoFocus
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            className="rounded-xl bg-zinc-700 px-4 py-3 text-zinc-300 active:bg-zinc-600 border border-zinc-600"
            onClick={onClose}
            disabled={submitting}
          >
            Отмена
          </button>
          <button
            className="rounded-xl bg-green-600 text-white px-4 py-3 active:bg-green-700 disabled:opacity-50"
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? "Добавление…" : "Добавить"}
          </button>
        </div>
      </div>
    </div>
  );
}

