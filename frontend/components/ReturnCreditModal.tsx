"use client";

import { useState, useMemo, useEffect } from "react";

type Props = {
  open: boolean;
  currentCredit: number;
  playerName: string | null;
  seatNo: number;
  onConfirm: (amount: number) => void;
  onCancel: () => void;
  loading?: boolean;
};

export default function ReturnCreditModal({
  open,
  currentCredit,
  playerName,
  seatNo,
  onConfirm,
  onCancel,
  loading = false,
}: Props) {
  const [creditAmount, setCreditAmount] = useState<string>("");

  // Prefill with current credit amount when modal opens
  useEffect(() => {
    if (open) {
      setCreditAmount(String(currentCredit));
    }
  }, [open, currentCredit]);

  const parsedCredit = useMemo(() => {
    const v = Number(creditAmount);
    return Number.isFinite(v) && v >= 0 ? v : 0;
  }, [creditAmount]);

  // Validation: credit amount must be between 1 and current credit
  const isValidAmount = parsedCredit >= 1 && parsedCredit <= currentCredit;

  if (!open) return null;

  const displayName = playerName || `Место ${seatNo}`;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      onClick={(e) => e.target === e.currentTarget && !loading && onCancel()}
    >
      <div
        className="bg-zinc-900 w-full max-w-md rounded-2xl p-5 shadow-xl mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-lg font-bold text-white mb-4">
          Возврат кредита
        </div>

        <div className="mb-4 rounded-xl bg-zinc-800 border border-zinc-700 p-4">
          <div className="text-sm text-zinc-300 mb-3">
            {displayName}
          </div>
          <div className="text-sm text-zinc-400">
            Текущий кредит: <span className="text-orange-400 font-semibold">{currentCredit} ₪</span>
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm text-zinc-400 mb-2">
            Сумма возврата (от 1 до {currentCredit})
          </label>
          <input
            type="number"
            inputMode="decimal"
            value={creditAmount}
            onChange={(e) => {
              const val = e.target.value;
              // Only allow positive numbers
              if (val === "" || (Number(val) >= 0)) {
                setCreditAmount(val);
              }
            }}
            className="w-full rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-white/15 placeholder-zinc-500"
            placeholder="Введите сумму"
            disabled={loading}
            min="1"
            max={currentCredit}
          />
          {parsedCredit > 0 && parsedCredit > currentCredit && (
            <div className="text-xs text-red-400 mt-1">
              Нельзя вернуть больше {currentCredit} ₪ кредита
            </div>
          )}
          {parsedCredit > 0 && parsedCredit < 1 && (
            <div className="text-xs text-red-400 mt-1">
              Минимальная сумма: 1 ₪
            </div>
          )}
        </div>

        <div className="space-y-3">
          <button
            className="w-full rounded-xl bg-green-600 text-white py-4 font-bold text-lg active:bg-green-700 disabled:opacity-60 focus:outline-none"
            onClick={() => {
              onConfirm(parsedCredit);
            }}
            disabled={loading || !isValidAmount}
          >
            {loading ? "Обработка..." : `Вернуть ${parsedCredit > 0 ? parsedCredit : "..."} ₪`}
          </button>
          <button
            className="w-full rounded-xl bg-zinc-700 text-zinc-300 py-4 font-bold text-lg active:bg-zinc-600 disabled:opacity-60 focus:outline-none border border-zinc-600"
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

