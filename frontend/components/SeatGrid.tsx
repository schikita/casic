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
    <div className="grid grid-cols-2 gap-2">
      {seats.map((seat) => (
        <button
          key={seat.seat_no}
          onClick={() => onSeatClick(seat)}
          className="rounded-xl p-3 bg-zinc-800 active:bg-zinc-700 text-left border border-zinc-700"
          aria-label={`Место ${seat.seat_no}${seat.player_name ? `, игрок: ${seat.player_name}` : ''}`}
        >
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500">#{seat.seat_no}</span>
            <span className="font-semibold truncate text-white">
              {seat.player_name ?? "—"}
            </span>
          </div>
          <div className="flex items-center tabular-nums font-bold">
            <span className="text-green-400">{seat.total}</span>
            <span className="text-zinc-500 mx-1">/</span>
            <span className="text-red-400">{seat.credit}</span>
          </div>
        </button>
      ))}
    </div>
  );
});
