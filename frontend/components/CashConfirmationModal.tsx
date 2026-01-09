"use client";

type Props = {
  open: boolean;
  amount: number;
  playerName: string | null;
  seatNo: number;
  onCash: () => void;
  onCredit: () => void;
  onCancel: () => void;
  loading?: boolean;
};

export default function CashConfirmationModal({
  open,
  amount,
  playerName,
  seatNo,
  onCash,
  onCredit,
  onCancel,
  loading = false,
}: Props) {
  if (!open) return null;

  const displayName = playerName || `Место ${seatNo}`;
  const isPositive = amount > 0;
  const actionText = isPositive ? "Выдал" : "Принял";

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
      onClick={(e) => e.target === e.currentTarget && !loading && onCancel()}
    >
      <div
        className="bg-white w-full max-w-md rounded-2xl p-5 shadow-xl mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-lg font-bold text-black mb-4">
          Способ оплаты
        </div>

        <div className="mb-6 rounded-xl bg-zinc-100 p-4">
          <div className="text-sm text-zinc-600 mb-2">
            {actionText} фишки
          </div>
          <div className="text-2xl font-bold text-zinc-900 mb-3">
            {Math.abs(amount)} ₪
          </div>
          <div className="text-sm text-zinc-700">
            {displayName}
          </div>
        </div>

        <div className="space-y-3">
          <button
            className="w-full rounded-xl bg-green-600 text-white py-4 font-bold text-lg active:bg-green-700 disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            onClick={onCash}
            disabled={loading}
          >
            💵 Наличные
          </button>
          <button
            className="w-full rounded-xl bg-blue-600 text-white py-4 font-bold text-lg active:bg-blue-700 disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-zinc-400"
            onClick={onCredit}
            disabled={loading}
          >
            📝 Кредит
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

