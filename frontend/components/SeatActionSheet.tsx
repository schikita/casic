"use client";

import { useMemo, useState, useEffect, useCallback } from "react";
import type { Seat, SeatHistoryEntry } from "@/lib/types";
import { CHIP_PRESETS } from "@/lib/constants";
import { apiJson } from "@/lib/api";

export default function SeatActionSheet({
  open,
  seat,
  sessionId,
  onClose,
  onAssign,
  onAdd,
  onClear,
}: {
  open: boolean;
  seat: Seat | null;
  sessionId: string | null;
  onClose: () => void;
  onAssign: (playerName: string | null, skipHistory?: boolean) => Promise<void>;
  onAdd: (amount: number) => void;
  onClear: () => Promise<void>;
}) {
  const [playerName, setPlayerName] = useState("");
  const [initialName, setInitialName] = useState<string | null>(null);
  const [customAmount, setCustomAmount] = useState<string>("");
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<SeatHistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [clearing, setClearing] = useState(false);

  // Sync playerName and initialName when panel opens
  useEffect(() => {
    if (open && seat) {
      const name = seat.player_name ?? "";
      setPlayerName(name);
      setInitialName(seat.player_name ?? null);
    }
  }, [open, seat?.seat_no]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Chips buttons are disabled until player name is entered
  const hasPlayerName = playerName.trim().length > 0;

  // Save name to backend if changed (used before chip operations)
  const saveNameIfChanged = useCallback(async () => {
    const currentTrimmed = playerName.trim() || null;
    if (currentTrimmed !== initialName) {
      await onAssign(currentTrimmed, false);
      setInitialName(currentTrimmed);
    }
  }, [playerName, initialName, onAssign]);

  const loadHistory = useCallback(async () => {
    if (!sessionId || !seat) return;
    setHistoryLoading(true);
    try {
      const data = await apiJson<SeatHistoryEntry[]>(
        `/api/sessions/${sessionId}/seats/${seat.seat_no}/history`
      );
      setHistory(data);
    } catch (e) {
      console.error("Failed to load history", e);
    } finally {
      setHistoryLoading(false);
    }
  }, [sessionId, seat]);

  const openHistory = async () => {
    await loadHistory();
    setShowHistory(true);
  };

  const formatDateTime = (isoString: string) => {
    const d = new Date(isoString);
    return d.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  if (!open || !seat) return null;

  // Fullscreen history overlay
  if (showHistory) {
    return (
      <div className="fixed inset-0 z-50 bg-zinc-900 flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-zinc-700">
          <div className="text-lg font-bold text-white">История места #{seatNo}</div>
          <button
            className="text-zinc-400 px-3 py-2 hover:text-white focus:outline-none"
            onClick={() => setShowHistory(false)}
          >
            Закрыть
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {historyLoading ? (
            <div className="text-center text-zinc-500 py-8">Загрузка...</div>
          ) : history.length === 0 ? (
            <div className="text-center text-zinc-500 py-8">История пуста</div>
          ) : (
            <div className="space-y-3">
              {history.map((entry, idx) => (
                <div
                  key={idx}
                  className="rounded-xl bg-zinc-800 border border-zinc-700 p-3"
                >
                  <div className="text-xs text-zinc-500 mb-1">
                    {formatDateTime(entry.created_at)}
                    {entry.created_by_username && (
                      <span className="ml-2">• {entry.created_by_username}</span>
                    )}
                  </div>
                  {entry.type === "player_left" ? (
                    <div className="text-sm text-orange-400 font-semibold">
                      🚪 Игрок ушёл: {entry.old_name || "—"}
                    </div>
                  ) : entry.type === "name_change" ? (
                    <div className="text-sm text-zinc-300">
                      <span className="font-semibold">Имя изменено:</span>{" "}
                      <span className="text-zinc-500">{entry.old_name || "—"}</span>
                      {" → "}
                      <span className="text-white font-medium">{entry.new_name || "—"}</span>
                    </div>
                  ) : (
                    <div className="text-sm">
                      <span
                        className={
                          (entry.amount ?? 0) >= 0
                            ? "text-green-400 font-bold"
                            : "text-red-400 font-bold"
                        }
                      >
                        {(entry.amount ?? 0) >= 0 ? "+" : ""}
                        {entry.amount}
                      </span>
                      {entry.payment_type && (
                        <span className="ml-2 text-zinc-500">
                          ({entry.payment_type === "credit" ? "📝 кредит" : "💵 наличные"})
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-end"
      onClick={onClose}
    >
      <div
        className="bg-zinc-900 w-full rounded-t-2xl p-4 pb-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="text-lg font-bold text-white">Место #{seatNo}</div>
          <button className="text-zinc-400 px-3 py-2 hover:text-white focus:outline-none" onClick={onClose}>
            Закрыть
          </button>
        </div>

        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <div className="text-xs text-zinc-500">Игрок</div>
            {(playerName || playerChips > 0) && (
              <button
                className="text-xs text-orange-400 font-medium px-2 py-1 rounded-lg hover:bg-orange-900/30 active:bg-orange-900/50 disabled:opacity-50"
                onClick={async () => {
                  setClearing(true);
                  try {
                    await onClear();
                    setPlayerName("");
                    setInitialName(null);
                  } finally {
                    setClearing(false);
                  }
                }}
                disabled={clearing}
              >
                {clearing ? "..." : "Сменить игрока"}
              </button>
            )}
          </div>
          <input
            value={playerName}
            onChange={(e) => {
              // Only update local state - backend save happens on blur
              setPlayerName(e.target.value);
            }}
            onBlur={() => {
              // Save to backend and log to history on blur if name changed from initial
              const currentTrimmed = playerName.trim() || null;
              if (currentTrimmed !== initialName) {
                onAssign(currentTrimmed, false);
                setInitialName(currentTrimmed);
              }
            }}
            className="w-full rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-zinc-500 placeholder-zinc-500"
            placeholder="Имя игрока (или пусто)"
          />
        </div>

        <div className="mb-3 rounded-xl bg-zinc-800 border border-zinc-700 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs text-zinc-500">Баланс игрока</div>
            <button
              className="text-xs text-blue-400 font-medium px-2 py-1 rounded-lg hover:bg-blue-900/30 active:bg-blue-900/50"
              onClick={openHistory}
            >
              История
            </button>
          </div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm text-zinc-400">Всего:</span>
            <span className="text-lg font-bold text-white">{playerChips} ₪</span>
          </div>
          {cashAmount > 0 && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-zinc-500">Наличные:</span>
              <span className="font-semibold text-green-400">{cashAmount} ₪</span>
            </div>
          )}
          {creditAmount > 0 && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-zinc-500">Кредит:</span>
              <span className="font-semibold text-orange-400">{creditAmount} ₪</span>
            </div>
          )}
        </div>

        <div className="mb-3">
          <div className="text-xs text-zinc-500 mb-2">Фишки</div>
          <div className="grid grid-cols-4 gap-2">
            {CHIP_PRESETS.map((v) => {
              const isDisabled = !hasPlayerName || !isMinusAmountValid(v);
              return (
                <button
                  key={v}
                  className={[
                    "py-3 rounded-xl text-white text-base font-bold",
                    v < 0
                      ? "bg-red-600 active:bg-red-700 hover:bg-red-700/90"
                      : "bg-green-600 active:bg-green-700 hover:bg-green-700/90",
                    isDisabled ? "opacity-50" : "",
                  ].join(" ")}
                  onClick={async () => {
                    if (isDisabled) return;
                    await saveNameIfChanged();
                    onAdd(v);
                    if (v < 0) onClose();
                  }}
                  disabled={isDisabled}
                >
                  {v > 0 ? "+" + String(v) : String(v)}
                </button>
              );
            })}
          </div>
        </div>

        <div className="mb-4">
          <div className="text-xs text-zinc-500 mb-2">Другая сумма</div>
          <div className="flex gap-2">
            <input
              inputMode="numeric"
              value={customAmount}
              onChange={(e) => setCustomAmount(e.target.value)}
              disabled={!hasPlayerName}
              className={[
                "flex-1 rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-zinc-500 placeholder-zinc-500",
                !hasPlayerName ? "opacity-50" : "",
              ].join(" ")}
              placeholder="например: 2500 или -2500"
            />
            <button
              className="rounded-xl bg-blue-600 text-white px-4 py-3 font-semibold active:bg-blue-700 disabled:opacity-60 focus:outline-none"
              disabled={!hasPlayerName || !parsedCustom || !isMinusAmountValid(parsedCustom)}
              onClick={async () => {
                if (!hasPlayerName || !parsedCustom || !isMinusAmountValid(parsedCustom)) return;
                await saveNameIfChanged();
                onAdd(parsedCustom);
                setCustomAmount("");
                if (parsedCustom < 0) onClose();
              }}
            >
              Применить
            </button>
          </div>
          {!hasPlayerName && (
            <div className="text-xs text-zinc-500 mt-1">
              Сначала введите имя игрока
            </div>
          )}
          {hasPlayerName && parsedCustom < 0 && playerChips + parsedCustom < 0 && (
            <div className="text-xs text-red-400 mt-1">
              Нельзя снять больше {playerChips} фишек
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
