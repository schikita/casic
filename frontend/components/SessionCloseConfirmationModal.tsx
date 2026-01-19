"use client";

import { useState, useEffect } from "react";

type CreditByPlayer = {
  seat_no: number;
  player_name: string | null;
  amount: number;
};

type ActiveDealer = {
  id: number;
  dealer_username: string;
};

type DealerRake = {
  assignment_id: number;
  rake: number;
};

type Props = {
  open: boolean;
  creditAmount: number;
  creditByPlayer?: CreditByPlayer[];
  activeDealers: ActiveDealer[];
  onConfirm: (dealerRakes: DealerRake[]) => void;
  onCancel: () => void;
  loading?: boolean;
};

export default function SessionCloseConfirmationModal({
  open,
  creditAmount,
  creditByPlayer = [],
  activeDealers,
  onConfirm,
  onCancel,
  loading = false,
}: Props) {
  const [dealerRakes, setDealerRakes] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);

  // Reset rake inputs when modal opens
  useEffect(() => {
    if (open) {
      const initial: Record<number, string> = {};
      activeDealers.forEach((d) => {
        initial[d.id] = "";
      });
      setDealerRakes(initial);
      setError(null);
    }
  }, [open, activeDealers]);

  const handleConfirm = () => {
    // Validate all rake inputs
    const rakes: DealerRake[] = [];
    for (const dealer of activeDealers) {
      const value = parseInt(dealerRakes[dealer.id] || "0", 10);
      if (isNaN(value) || value < 0) {
        setError(`Введите корректную сумму рейка для ${dealer.dealer_username}`);
        return;
      }
      rakes.push({ assignment_id: dealer.id, rake: value });
    }
    setError(null);
    onConfirm(rakes);
  };

  if (!open) return null;

  const hasCredit = creditAmount > 0;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      onClick={(e) => e.target === e.currentTarget && !loading && onCancel()}
    >
      <div
        className="bg-white w-full max-w-md rounded-2xl p-5 shadow-xl mx-4 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="text-lg font-bold text-black">
            Закрыть сессию
          </div>
          <button
            className="text-zinc-600 px-3 py-2 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            onClick={onCancel}
            disabled={loading}
          >
            Закрыть
          </button>
        </div>

        {hasCredit && (
          <div className="mb-6 rounded-xl bg-red-50 border border-red-200 p-4">
            <div className="text-sm text-red-700 font-semibold mb-3">
              ⚠️ Внимание: Кредит в сессии
            </div>
            <div className="text-2xl font-bold text-red-600 mb-3">
              Всего: {creditAmount} ₪
            </div>
            {creditByPlayer.length > 0 && (
              <div className="mb-3 space-y-2">
                <div className="text-xs font-semibold text-red-700 mb-2">
                  Кредит по игрокам:
                </div>
                {creditByPlayer.map((credit) => (
                  <div
                    key={credit.seat_no}
                    className="flex justify-between text-xs text-red-600 bg-red-100 rounded-xl px-2 py-1"
                  >
                    <span>
                      {credit.player_name || `Место ${credit.seat_no}`}
                    </span>
                    <span className="font-semibold">{credit.amount} ₪</span>
                  </div>
                ))}
              </div>
            )}
            <div className="text-xs text-red-600">
              Игроки должны деньги. Убедитесь, что это учтено перед закрытием.
            </div>
          </div>
        )}

        {!hasCredit && (
          <div className="mb-6 rounded-xl bg-green-50 border border-green-200 p-4">
            <div className="text-sm text-green-700 font-semibold">
              ✓ Нет кредита в сессии
            </div>
          </div>
        )}

        {/* Dealer rake inputs */}
        {activeDealers.length > 0 && (
          <div className="mb-6 rounded-xl bg-zinc-50 border border-zinc-200 p-4">
            <div className="text-sm text-zinc-700 font-semibold mb-3">
              Рейк по дилерам
            </div>
            <div className="space-y-3">
              {activeDealers.map((dealer) => (
                <div key={dealer.id}>
                  <label className="block text-xs text-zinc-600 mb-1">
                    {dealer.dealer_username}
                  </label>
                  <input
                    type="number"
                    inputMode="numeric"
                    min="0"
                    className="w-full rounded-xl border border-zinc-300 bg-white text-black px-3 py-2 text-base focus:outline-none focus:ring-2 focus:ring-zinc-400"
                    value={dealerRakes[dealer.id] || ""}
                    onChange={(e) =>
                      setDealerRakes((prev) => ({
                        ...prev,
                        [dealer.id]: e.target.value,
                      }))
                    }
                    placeholder="0"
                    disabled={loading}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 rounded-xl bg-red-50 text-red-700 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <div className="space-y-3">
          <button
            className="w-full rounded-xl bg-red-600 text-white py-4 font-bold text-lg active:bg-red-700 disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            onClick={handleConfirm}
            disabled={loading}
          >
            Закрыть сессию
          </button>
          <button
            className="w-full rounded-xl bg-zinc-300 text-zinc-900 py-4 font-bold text-lg active:bg-zinc-400 disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            onClick={onCancel}
            disabled={loading}
          >
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}

