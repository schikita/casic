"use client";

type CreditByPlayer = {
  seat_no: number;
  player_name: string | null;
  amount: number;
};

type Props = {
  open: boolean;
  creditAmount: number;
  creditByPlayer?: CreditByPlayer[];
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
};

export default function SessionCloseConfirmationModal({
  open,
  creditAmount,
  creditByPlayer = [],
  onConfirm,
  onCancel,
  loading = false,
}: Props) {
  if (!open) return null;

  const hasCredit = creditAmount > 0;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      onClick={(e) => e.target === e.currentTarget && !loading && onCancel()}
    >
      <div
        className="bg-zinc-900 w-full max-w-md rounded-2xl p-5 shadow-xl mx-4 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="text-lg font-bold text-white">
            Закрыть сессию
          </div>
          <button
            className="text-zinc-400 px-3 py-2 disabled:opacity-50 hover:text-white focus:outline-none"
            onClick={onCancel}
            disabled={loading}
          >
            Закрыть
          </button>
        </div>

        {hasCredit && (
          <div className="mb-6 rounded-xl bg-red-900/40 border border-red-700 p-4">
            <div className="text-sm text-red-300 font-semibold mb-3">
              ⚠️ Внимание: Кредит в сессии
            </div>
            <div className="text-2xl font-bold text-red-400 mb-3">
              Всего: {creditAmount} ₪
            </div>
            {creditByPlayer.length > 0 && (
              <div className="mb-3 space-y-2">
                <div className="text-xs font-semibold text-red-300 mb-2">
                  Кредит по игрокам:
                </div>
                {creditByPlayer.map((credit) => (
                  <div
                    key={credit.seat_no}
                    className="flex justify-between text-xs text-red-300 bg-red-900/50 rounded-xl px-2 py-1"
                  >
                    <span>
                      {credit.player_name || `Место ${credit.seat_no}`}
                    </span>
                    <span className="font-semibold">{credit.amount} ₪</span>
                  </div>
                ))}
              </div>
            )}
            <div className="text-xs text-red-400">
              Игроки должны деньги. Убедитесь, что это учтено перед закрытием.
            </div>
          </div>
        )}

        {!hasCredit && (
          <div className="mb-6 rounded-xl bg-green-900/40 border border-green-700 p-4">
            <div className="text-sm text-green-300 font-semibold">
              ✓ Нет кредита в сессии
            </div>
          </div>
        )}

        <div className="space-y-3">
          <button
            className="w-full rounded-xl bg-red-600 text-white py-4 font-bold text-lg active:bg-red-700 disabled:opacity-60 focus:outline-none"
            onClick={onConfirm}
            disabled={loading}
          >
            Закрыть сессию
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

