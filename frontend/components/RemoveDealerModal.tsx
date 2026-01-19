"use client";

import { useState, useEffect } from "react";
import { apiJson } from "@/lib/api";

type Props = {
  open: boolean;
  sessionId: string;
  assignmentId: number;
  dealerName: string;
  onClose: () => void;
  onDealerRemoved: () => void;
};

export default function RemoveDealerModal({
  open,
  sessionId,
  assignmentId,
  dealerName,
  onClose,
  onDealerRemoved,
}: Props) {
  const [rake, setRake] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setRake("");
      setError(null);
    }
  }, [open]);

  const handleSubmit = async () => {
    const rakeValue = parseInt(rake, 10);
    if (isNaN(rakeValue) || rakeValue < 0) {
      setError("Введите корректную сумму рейка (0 или больше)");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await apiJson(`/api/sessions/${sessionId}/remove-dealer`, {
        method: "POST",
        body: JSON.stringify({
          assignment_id: assignmentId,
          rake: rakeValue,
        }),
      });
      onDealerRemoved();
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
        className="bg-white w-full max-w-md rounded-2xl p-5 shadow-xl mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="text-lg font-bold text-black">Завершить смену дилера</div>
          <button
            className="text-zinc-600 px-3 py-2 disabled:opacity-50"
            onClick={onClose}
            disabled={submitting}
          >
            ✕
          </button>
        </div>

        <div className="mb-4 text-sm text-zinc-700">
          Дилер: <span className="font-semibold text-black">{dealerName}</span>
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-50 text-red-700 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <div className="mb-4">
          <label className="block text-sm text-zinc-600 mb-1">
            Рейк за смену (₪)
          </label>
          <input
            type="number"
            inputMode="numeric"
            min="0"
            className="w-full rounded-xl border border-zinc-300 bg-white text-black px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-zinc-400"
            value={rake}
            onChange={(e) => setRake(e.target.value)}
            placeholder="0"
            disabled={submitting}
            autoFocus
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            className="rounded-xl bg-zinc-100 px-4 py-3 text-zinc-700 active:bg-zinc-200"
            onClick={onClose}
            disabled={submitting}
          >
            Отмена
          </button>
          <button
            className="rounded-xl bg-red-600 text-white px-4 py-3 active:bg-red-700 disabled:opacity-50"
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? "Завершение…" : "Завершить"}
          </button>
        </div>
      </div>
    </div>
  );
}

