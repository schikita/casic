"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Staff } from "@/lib/types";

type Props = {
  open: boolean;
  sessionId: string;
  activeWaiterIds: number[];
  onClose: () => void;
  onWaiterAdded: () => void;
};

export default function AddWaiterModal({
  open,
  sessionId,
  activeWaiterIds,
  onClose,
  onWaiterAdded,
}: Props) {
  const [waiters, setWaiters] = useState<Staff[]>([]);
  const [selectedWaiterId, setSelectedWaiterId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setError(null);
      setSelectedWaiterId(null);
      loadWaiters();
    }
  }, [open]);

  const loadWaiters = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch("/api/sessions/available-waiters");
      if (!res.ok) {
        throw new Error("Ошибка загрузки официантов");
      }
      const data = await res.json();
      // Filter out waiters already assigned to this session
      const availableWaiters = data.filter((w: Staff) => !activeWaiterIds.includes(w.id));
      setWaiters(availableWaiters);
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!selectedWaiterId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/sessions/${sessionId}/add-waiter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ waiter_id: selectedWaiterId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка добавления официанта");
      }
      onWaiterAdded();
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
      <div className="bg-zinc-800 rounded-2xl p-6 w-[90%] max-w-md shadow-xl">
        <h2 className="text-xl font-bold mb-4 text-white">Добавить официанта</h2>

        {loading ? (
          <div className="text-center py-8 text-zinc-400">Загрузка...</div>
        ) : (
          <>
            <div className="mb-4">
              <label className="block text-sm font-medium mb-2 text-white">
                Выберите официанта:
              </label>
              <select
                className="w-full border border-zinc-600 bg-zinc-700 text-white rounded-lg px-3 py-2"
                value={selectedWaiterId ?? ""}
                onChange={(e) => setSelectedWaiterId(Number(e.target.value))}
                disabled={submitting}
              >
                <option value="">-- Выберите --</option>
                {waiters.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.username}
                  </option>
                ))}
              </select>
            </div>

            {error && (
              <div className="mb-4 p-3 bg-red-900/50 text-red-200 rounded-lg text-sm">
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
                className="rounded-xl bg-green-600 text-white px-4 py-3 active:bg-green-700 disabled:opacity-50"
                onClick={handleSubmit}
                disabled={!selectedWaiterId || submitting}
              >
                {submitting ? "Добавление..." : "Добавить"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

