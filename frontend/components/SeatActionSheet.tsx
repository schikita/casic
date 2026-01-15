"use client";

import { useMemo, useState } from "react";
import type { Seat } from "@/lib/types";
import { CHIP_PRESETS } from "@/lib/constants";

export default function SeatActionSheet({
  open,
  seat,
  onClose,
  onAssign,
  onAdd,
}: {
  open: boolean;
  seat: Seat | null;
  onClose: () => void;
  onAssign: (playerName: string | null) => Promise<void>;
  onAdd: (amount: number) => void;
}) {
  const [playerName, setPlayerName] = useState("");
  const [customAmount, setCustomAmount] = useState<string>("");

  const seatNo = seat?.seat_no ?? 0;
  const playerChips = seat?.total ?? 0;
  const cashAmount = seat?.cash ?? 0;
  const creditAmount = seat?.credit ?? 0;

  const parsedCustom = useMemo(() => {
    const v = Number(customAmount);
    return Number.isFinite(v) ? v : 0;
  }, [customAmount]);

  const isMinusAmountValid = (amount: number) => {
    if (amount >= 0) return true;
    return playerChips + amount >= 0;
  };

  if (!open || !seat) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-end"
      onClick={onClose}
    >
      <div
        className="bg-white w-full rounded-t-2xl p-4 pb-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="text-lg font-bold text-black">Место #{seatNo}</div>
          <button className="text-zinc-600 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-zinc-400" onClick={onClose}>
            Закрыть
          </button>
        </div>

        <div className="mb-3">
          <div className="text-xs text-zinc-500 mb-1">Игрок</div>
          <div className="flex gap-2">
            <input
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
              className="flex-1 rounded-xl border border-zinc-300 bg-white text-black px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-zinc-400 placeholder-zinc-600"
              placeholder="Имя игрока (или пусто)"
            />
            <button
              className="rounded-xl bg-zinc-900 text-white px-4 py-3 font-semibold focus:outline-none focus:ring-2 focus:ring-zinc-400"
              onClick={async () => {
                const name = playerName.trim();
                await onAssign(name ? name : null);
              }}
            >
              OK
            </button>
          </div>
        </div>

        {playerChips > 0 && (cashAmount > 0 || creditAmount > 0) && (
          <div className="mb-3 rounded-xl bg-zinc-50 border border-zinc-200 p-3">
            <div className="text-xs text-zinc-500 mb-2">Баланс игрока</div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-zinc-700">Всего:</span>
              <span className="text-lg font-bold text-zinc-900">{playerChips} ₪</span>
            </div>
            {cashAmount > 0 && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-zinc-600">Наличные:</span>
                <span className="font-semibold text-green-600">{cashAmount} ₪</span>
              </div>
            )}
            {creditAmount > 0 && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-zinc-600">Кредит:</span>
                <span className="font-semibold text-orange-600">{creditAmount} ₪</span>
              </div>
            )}
          </div>
        )}

        <div className="mb-3">
          <div className="text-xs text-zinc-500 mb-2">Фишки</div>
          <div className="grid grid-cols-4 gap-2">
            {CHIP_PRESETS.map((v) => (
              <button
                key={v}
                className={[
                  "py-3 rounded-xl text-white text-base font-bold",
                  v < 0
                    ? "bg-red-600 active:bg-red-700 hover:bg-red-700/90"
                    : "bg-green-600 active:bg-green-700 hover:bg-green-700/90",
                  !isMinusAmountValid(v) ? "opacity-50" : "",
                ].join(" ")}
                onClick={() => {
                  if (!isMinusAmountValid(v)) return;
                  onAdd(v);
                  if (v < 0) onClose();
                }}
                disabled={!isMinusAmountValid(v)}
              >
                {v > 0 ? "+" + String(v) : String(v)}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-4">
          <div className="text-xs text-zinc-500 mb-2">Другая сумма</div>
          <div className="flex gap-2">
            <input
              inputMode="numeric"
              value={customAmount}
              onChange={(e) => setCustomAmount(e.target.value)}
              className="flex-1 rounded-xl border border-zinc-300 bg-white text-black px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-zinc-400 placeholder-zinc-600"
              placeholder="например: 2500 или -2500"
            />
            <button
              className="rounded-xl bg-blue-600 text-white px-4 py-3 font-semibold active:bg-blue-700 disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-zinc-400"
              disabled={!parsedCustom || !isMinusAmountValid(parsedCustom)}
              onClick={() => {
                if (!parsedCustom || !isMinusAmountValid(parsedCustom)) return;
                onAdd(parsedCustom);
                setCustomAmount("");
                if (parsedCustom < 0) onClose();
              }}
            >
              Применить
            </button>
          </div>
          {parsedCustom < 0 && playerChips + parsedCustom < 0 && (
            <div className="text-xs text-red-600 mt-1">
              Нельзя снять больше {playerChips} фишек
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
