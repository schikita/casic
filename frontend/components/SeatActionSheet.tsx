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
  onAdd: (amount: number) => Promise<void>;
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

  const parsedCustom = useMemo(() => {
    const v = Number(customAmount);
    return Number.isFinite(v) ? v : 0;
  }, [customAmount]);

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
                ].join(" ")}
                onClick={async () => {
                  await onAdd(v);
                }}
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
              disabled={!parsedCustom}
              onClick={async () => {
                if (!parsedCustom) return;
                await onAdd(parsedCustom);
                setCustomAmount("");
              }}
            >
              Применить
            </button>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            className="flex-1 rounded-xl bg-zinc-200 px-4 py-3 font-semibold active:bg-zinc-300 disabled:opacity-50"
            disabled={!seat || seat.total === 0}
            onClick={async () => {
              if (!seat || seat.total === 0) return;
              await onUndo();
            }}
          >
            Undo
          </button>
          <button
            className="flex-1 rounded-xl bg-zinc-900 text-white px-4 py-3 font-semibold active:bg-black"
            onClick={onClose}
          >
            Готово
          </button>
        </div>
      </div>
    </div>
  );
}
