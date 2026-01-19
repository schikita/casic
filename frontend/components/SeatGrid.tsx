"use client";

import { memo } from "react";
import type { Seat } from "@/lib/types";

export default memo(function SeatGrid({
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
          className="rounded-xl p-4 bg-zinc-100 active:bg-zinc-200 text-left shadow-sm"
          aria-label={`Место ${seat.seat_no}${seat.player_name ? `, игрок: ${seat.player_name}` : ''}`}
        >
          <div className="text-xs text-zinc-500">#{seat.seat_no}</div>
          <div className="font-semibold truncate text-black">
            {seat.player_name ?? "—"}
          </div>
          {/* Display chips: green for cash-only, red for credit with playable/total */}
          {seat.credit > 0 ? (
            <div className="text-sm font-semibold tabular-nums text-red-600">
              {seat.total}/{seat.credit}
            </div>
          ) : seat.total > 0 ? (
            <div className="text-lg font-bold tabular-nums text-green-500">
              {seat.total}
            </div>
          ) : (
            <div
              className={[
                "text-lg font-bold tabular-nums",
                seat.total < 0 ? "text-red-500" : "text-zinc-800",
              ].join(" ")}
            >
              {seat.total}
            </div>
          )}
        </button>
      ))}
    </div>
  );
});
