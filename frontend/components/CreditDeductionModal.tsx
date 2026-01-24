"use client";

import { useState, useMemo } from "react";

type Props = {
  open: boolean;
  cashoutAmount: number; // Positive number representing amount being cashed out
  currentCredit: number;
  currentCash: number;
  playerName: string | null;
  seatNo: number;
  onConfirm: (creditToDeduct: number) => void;
  onCancel: () => void;
  loading?: boolean;
};

export default function CreditDeductionModal({
  open,
  cashoutAmount,
  currentCredit,
  currentCash,
  playerName,
  seatNo,
  onConfirm,
  onCancel,
  loading = false,
}: Props) {
  const [creditAmount, setCreditAmount] = useState<string>("");

  const parsedCredit = useMemo(() => {
    const v = Number(creditAmount);
    return Number.isFinite(v) && v >= 0 ? v : 0;
  }, [creditAmount]);

  // Validation: credit amount must not exceed current credit
  const creditExceedsAvailable = parsedCredit > currentCredit;

  // Validation: cash portion must not exceed current cash
  const cashPortion = cashoutAmount - parsedCredit;
  const cashExceedsAvailable = cashPortion > currentCash;

  const isValidAmount = !creditExceedsAvailable && !cashExceedsAvailable;

  // Debug logging
  console.log("=== CREDIT DEDUCTION MODAL DEBUG ===");
  console.log("cashoutAmount:", cashoutAmount);
  console.log("currentCredit:", currentCredit);
  console.log("currentCash:", currentCash);
  console.log("creditAmount (input):", creditAmount);
  console.log("parsedCredit:", parsedCredit);
  console.log("cashPortion:", cashPortion);
  console.log("creditExceedsAvailable:", creditExceedsAvailable);
  console.log("cashExceedsAvailable:", cashExceedsAvailable);
  console.log("isValidAmount:", isValidAmount);
  console.log("=== END DEBUG ===");

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
          Списать кредит?
        </div>

        <div className="mb-4 rounded-xl bg-zinc-800 border border-zinc-700 p-4">
          <div className="text-sm text-zinc-400 mb-2">
            Снимается со стола
          </div>
          <div className="text-2xl font-bold text-white mb-3">
            {cashoutAmount} ₪
          </div>
          <div className="text-sm text-zinc-300 mb-3">
            {displayName}
          </div>
          <div className="text-sm text-zinc-400">
            Текущий кредит: <span className="text-blue-400 font-semibold">{currentCredit} ₪</span>
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm text-zinc-400 mb-2">
            Сумма кредита для списания (опционально)
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
            placeholder="0"
            disabled={loading}
            min="0"
            max={currentCredit}
          />
          {parsedCredit > 0 && creditExceedsAvailable && (
            <div className="text-xs text-red-400 mt-1">
              Нельзя списать больше {currentCredit} ₪ кредита
            </div>
          )}
          {parsedCredit > 0 && cashExceedsAvailable && (
            <div className="text-xs text-red-400 mt-1">
              Недостаточно наличных. Нужно {cashPortion} ₪, доступно {currentCash} ₪
            </div>
          )}
        </div>

        <div className="space-y-3">
          <button
            className="w-full rounded-xl bg-green-600 text-white py-4 font-bold text-lg active:bg-green-700 disabled:opacity-60 focus:outline-none"
            onClick={() => {
              console.log("=== BUTTON CLICKED ===");
              console.log("parsedCredit:", parsedCredit);
              console.log("Calling onConfirm with:", parsedCredit);
              onConfirm(parsedCredit);
              console.log("=== onConfirm called ===");
            }}
            disabled={loading || !isValidAmount}
          >
            {parsedCredit > 0 ? `Снять и списать ${parsedCredit} ₪` : "Снять без списания кредита"}
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

