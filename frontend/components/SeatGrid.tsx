"use client";

import type { Seat } from "@/lib/types";

export default function SeatGrid({
  seats,
  onSeatClick,
}: {
  seats: Seat[];
  onSeatClick: (seat: Seat) => void;
}) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {seats.map((seat) => (
        <button
          key={seat.seat_no}
          onClick={() => onSeatClick(seat)}
          className="rounded-xl p-3 bg-zinc-100 active:bg-zinc-200 text-left shadow-sm"
        >
          <div className="text-xs text-zinc-500">#{seat.seat_no}</div>
          <div className="font-semibold truncate text-black">
            {seat.player_name ?? "—"}
          </div>
          <div
            className={[
              "text-lg font-bold tabular-nums",
              seat.total < 0
                ? "text-red-500"
                : seat.total > 0
                ? "text-green-500"
                : "text-zinc-800",
            ].join(" ")}
          >
            {seat.total}
          </div>
        </button>
      ))}
    </div>
  );
}
