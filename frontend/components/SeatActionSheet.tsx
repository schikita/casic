"use client";

import { useEffect, useMemo, useState } from "react";
import type { Seat } from "@/lib/types";

const PRESETS = [-100, -500, -1000, -5000, 100, 500, 1000, 5000];

export default function SeatActionSheet({
  open,
  seat,
  onClose,
  onAssign,
  onAdd,
  onUndo,
}: {
  open: boolean;
  seat: Seat | null;
  onClose: () => void;
  onAssign: (playerName: string | null) => Promise<void>;
  onAdd: (amount: number) => void;
  onUndo: () => Promise<void>;
}) {
  const [playerName, setPlayerName] = useState("");
  const [customAmount, setCustomAmount] = useState<string>("");

  useEffect(() => {
    if (!seat) return;
    setPlayerName(seat.player_name ?? "");
    setCustomAmount("");
  }, [seat?.seat_no]);

  const seatNo = seat?.seat_no ?? 0;
  const playerChips = seat?.total ?? 0;

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
          <button className="text-zinc-600 px-3 py-2" onClick={onClose}>
            Закрыть
          </button>
        </div>

        <div className="mb-3">
          <div className="text-xs text-zinc-500 mb-1">Игрок</div>
          <div className="flex gap-2">
            <input
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
              className="flex-1 rounded-xl border px-3 py-3 text-base text-black placeholder-zinc-600"
              placeholder="Имя игрока (или пусто)"
            />
            <button
              className="rounded-xl bg-zinc-900 text-white px-4 py-3 font-semibold"
              onClick={async () => {
                const name = playerName.trim();
                await onAssign(name ? name : null);
              }}
            >
              OK
            </button>
          </div>
        </div>

        <div className="mb-3">
          <div className="text-xs text-zinc-500 mb-2">Фишки</div>
          <div className="grid grid-cols-4 gap-2">
            {PRESETS.map((v) => (
              <button
                key={v}
                className={[
                  "py-3 rounded-xl text-white text-base font-bold",
                  v < 0
                    ? "bg-red-600 active:bg-red-700"
                    : "bg-green-600 active:bg-green-700",
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
              className="flex-1 rounded-xl border px-3 py-3 text-base text-black placeholder-zinc-600"
              placeholder="например: 2500 или -2500"
            />
            <button
              className="rounded-xl bg-blue-600 text-white px-4 py-3 font-semibold active:bg-blue-700 disabled:opacity-60"
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
