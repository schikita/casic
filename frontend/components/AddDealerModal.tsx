"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import type { Staff } from "@/lib/types";

type Props = {
  open: boolean;
  sessionId: string;
  onClose: () => void;
  onDealerAdded: () => void;
};

export default function AddDealerModal({
  open,
  sessionId,
  onClose,
  onDealerAdded,
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
      const res = await apiFetch(`/api/sessions/available-dealers?session_id=${sessionId}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка загрузки дилеров");
      }
      const data = await res.json();
      setDealers(data);
      if (data.length > 0) {
        setSelectedDealerId(data[0].id);
      }
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

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
      const res = await apiFetch(`/api/sessions/${sessionId}/add-dealer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dealer_id: selectedDealerId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка добавления дилера");
      }
      onDealerAdded();
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
          <div className="text-lg font-bold text-black">Добавить дилера</div>
          <button
            className="text-zinc-600 px-3 py-2 disabled:opacity-50"
            onClick={onClose}
            disabled={submitting}
          >
            ✕
          </button>
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-50 text-red-700 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-zinc-500 text-sm mb-3">Загрузка доступных дилеров…</div>
        ) : dealers.length === 0 ? (
          <div className="text-zinc-500 text-sm mb-3">Нет доступных дилеров для добавления</div>
        ) : (
          <div className="mb-4">
            <label className="block text-sm text-zinc-600 mb-1">Выберите дилера</label>
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
            className="rounded-xl bg-green-600 text-white px-4 py-3 active:bg-green-700 disabled:opacity-50"
            onClick={handleSubmit}
            disabled={submitting || loading || dealers.length === 0}
          >
            {submitting ? "Добавление…" : "Добавить"}
          </button>
        </div>
      </div>
    </div>
  );
}

