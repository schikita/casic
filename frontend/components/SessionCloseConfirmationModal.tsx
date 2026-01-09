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

        <div className="space-y-3">
          <button
            className="w-full rounded-xl bg-red-600 text-white py-4 font-bold text-lg active:bg-red-700 disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            onClick={onConfirm}
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

