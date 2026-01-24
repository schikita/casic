"use client";

import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

type Props = {
  open: boolean;
  sessionId: string;
  assignmentId: number;
  waiterName: string;
  onClose: () => void;
  onWaiterRemoved: () => void;
};

export default function RemoveWaiterModal({
  open,
  sessionId,
  assignmentId,
  waiterName,
  onClose,
  onWaiterRemoved,
}: Props) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setError(null);
    }
  }, [open]);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await apiJson(`/api/sessions/${sessionId}/remove-waiter`, {
        method: "POST",
        body: JSON.stringify({ assignment_id: assignmentId }),
      });
      onWaiterRemoved();
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
          <div className="text-lg font-bold text-white">Завершить смену официанта</div>
          <button
            className="text-zinc-400 px-3 py-2 disabled:opacity-50 hover:text-white"
            onClick={onClose}
            disabled={submitting}
          >
            ✕
          </button>
        </div>

        <div className="mb-4 text-sm text-zinc-300">
          Завершить смену официанта <span className="font-semibold text-white">{waiterName}</span>?
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-900/50 text-red-200 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          <button
            className="rounded-xl bg-zinc-700 px-4 py-3 text-zinc-300 active:bg-zinc-600 border border-zinc-600"
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

