"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import TopMenu from "@/components/TopMenu";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import { apiFetch } from "@/lib/api";
import { formatMoney, formatTime } from "@/lib/utils";
import type { Table } from "@/lib/types";

type SessionDealerAssignment = {
  id: number;
  dealer_id: number;
  dealer_username: string;
  started_at: string;
  ended_at: string | null;
  rake: number | null;
};

type ClosedSession = {
  id: string;
  table_id: number;
  table_name: string;
  date: string;
  created_at: string;
  closed_at: string;
  dealer_id: number | null;
  waiter_id: number | null;
  dealer_username: string | null;
  waiter_username: string | null;
  chips_in_play: number | null;
  total_rake: number;
  total_buyins: number;
  total_cashouts: number;
  dealer_assignments: SessionDealerAssignment[];
};

// Get working day boundaries for a given calendar date
// Working day: 20:00 (8 PM) to 18:00 (6 PM) of next day
function getWorkingDayBoundaries(date: Date): { start: Date; end: Date; label: string } {
  const start = new Date(date);
  start.setHours(20, 0, 0, 0);
  
  const end = new Date(date);
  end.setDate(end.getDate() + 1);
  end.setHours(18, 0, 0, 0);
  
  // Format the working day label (e.g., "09 января 20:00 - 10 января 18:00")
  const startDateStr = start.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "long",
  });
  const startTimeStr = start.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const endDateStr = end.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "long",
  });
  const endTimeStr = end.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
  
  const label = `${startDateStr} ${startTimeStr} - ${endDateStr} ${endTimeStr}`;
  
  return { start, end, label };
}

// Get the working day that a session belongs to based on its created_at time
function getSessionWorkingDay(session: ClosedSession): { start: Date; end: Date; label: string } {
  const createdAt = new Date(session.created_at);
  const hour = createdAt.getHours();
  
  // If session started before 18:00, it belongs to the working day that started yesterday
  // If session started at 18:00 or later, it belongs to the working day that started today
  const workingDayStart = new Date(createdAt);
  if (hour < 18) {
    workingDayStart.setDate(workingDayStart.getDate() - 1);
  }
  
  return getWorkingDayBoundaries(workingDayStart);
}

// Group sessions by working day (20:00 to 18:00 next day)
function groupSessionsByDay(sessions: ClosedSession[]): Map<string, ClosedSession[]> {
  const groups = new Map<string, ClosedSession[]>();
  
  for (const session of sessions) {
    const workingDay = getSessionWorkingDay(session);
    const label = workingDay.label;
    
    if (!groups.has(label)) {
      groups.set(label, []);
    }
    groups.get(label)!.push(session);
  }
  
  return groups;
}

export default function SessionsPage() {
  const { user } = useAuth();
  const [sessions, setSessions] = useState<ClosedSession[]>([]);
  const [tables, setTables] = useState<Table[]>([]);
  const [selectedTableId, setSelectedTableId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTables = useCallback(async () => {
    try {
      const res = await apiFetch("/api/admin/tables");
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка загрузки столов");
      }
      const tablesData = await res.json();
      setTables(tablesData);
      
      // Auto-select first table for superadmin, or user's table for table_admin
      if (user?.role === "superadmin" && tablesData.length > 0 && !selectedTableId) {
        setSelectedTableId(tablesData[0].id);
      } else if (user?.role === "table_admin" && user.table_id && !selectedTableId) {
        setSelectedTableId(user.table_id);
      }
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка загрузки столов");
    }
  }, [user, selectedTableId]);

  const loadSessions = useCallback(async () => {
    if (!selectedTableId) return;
    
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/admin/closed-sessions?table_id=${selectedTableId}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка загрузки сессий");
      }
      setSessions(await res.json());
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка");
    } finally {
      setLoading(false);
    }
  }, [selectedTableId]);

  // Load tables on mount
  useEffect(() => {
    if (user && (user.role === "superadmin" || user.role === "table_admin")) {
      loadTables();
    }
  }, [user, loadTables]);

  // Load sessions when table is selected
  useEffect(() => {
    if (selectedTableId) {
      loadSessions();
    }
  }, [selectedTableId, loadSessions]);

  const sessionsByDay = useMemo(() => groupSessionsByDay(sessions), [sessions]);
  const days = useMemo(() => Array.from(sessionsByDay.keys()), [sessionsByDay]);

  if (!user) {
    return (
      <RequireAuth>
        <div className="p-4 text-white">Загрузка…</div>
      </RequireAuth>
    );
  }

  if (user.role !== "superadmin" && user.role !== "table_admin") {
    return (
      <RequireAuth>
        <main className="p-4 max-w-md mx-auto">
          <TopMenu />
          <div className="mt-4 rounded-xl bg-zinc-900 text-white px-4 py-3">
            Доступ запрещён. Только для администраторов столов.
          </div>
        </main>
      </RequireAuth>
    );
  }

  return (
    <RequireAuth>
      <main className="p-3 max-w-md mx-auto pb-20">
        <TopMenu />

        <div className="flex items-center justify-between mb-3">
          <div className="text-xl font-bold text-white">История сессий</div>
          <button
            className="rounded-xl bg-black text-white px-3 py-2 text-sm disabled:opacity-60 hover:bg-zinc-800/90"
            onClick={() => {
              if (selectedTableId) {
                loadSessions();
              }
            }}
            disabled={loading || !selectedTableId}
          >
            Обновить
          </button>
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-900/50 text-red-200 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {/* Table selector for superadmin */}
        {user.role === "superadmin" && (
          <div className="rounded-xl bg-zinc-900 p-4 mb-3">
            <div className="text-white font-semibold mb-2">Выберите стол</div>
            <select
              className="w-full rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-white/15 placeholder-zinc-500"
              value={selectedTableId ?? ""}
              onChange={(e) => setSelectedTableId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">-- Выберите стол --</option>
              {tables.map((table) => (
                <option key={table.id} value={table.id}>
                  {table.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Display table name for table_admin */}
        {user.role === "table_admin" && tables.length > 0 && (
          <div className="rounded-xl bg-zinc-900 p-4 mb-3">
            <div className="text-white font-semibold mb-1">Стол</div>
            <div className="text-zinc-300">{tables[0]?.name}</div>
          </div>
        )}

        {/* Sessions grouped by day */}
        <div className="space-y-4">
          {loading && (
            <div className="fixed bottom-4 left-0 right-0 flex justify-center pointer-events-none">
              <div className="rounded-xl bg-black/80 text-white px-4 py-2 text-sm">
                Загрузка…
              </div>
            </div>
          )}

          {!loading && !selectedTableId && (
            <div className="rounded-xl bg-zinc-900 text-white/70 px-3 py-3 text-sm rounded-xl">
              Выберите стол для просмотра истории
            </div>
          )}

          {!loading && selectedTableId && sessions.length === 0 && (
            <div className="rounded-xl bg-zinc-900 text-white/70 px-3 py-3 text-sm rounded-xl">
              Нет закрытых сессий
            </div>
          )}

          {!loading && selectedTableId && days.map((day, dayIndex) => {
            const daySessions = sessionsByDay.get(day) || [];
            const showDaySeparator = dayIndex > 0;

            return (
              <div key={day}>
                {showDaySeparator && (
                  <div className="flex items-center gap-3 my-4">
                    <div className="flex-1 h-px bg-zinc-700" />
                    <span className="text-xs text-zinc-500">{day}</span>
                    <div className="flex-1 h-px bg-zinc-700" />
                  </div>
                )}

                {!showDaySeparator && (
                  <div className="flex items-center gap-3 mb-4">
                    <div className="flex-1 h-px bg-zinc-700" />
                    <span className="text-xs text-zinc-500">{day}</span>
                    <div className="flex-1 h-px bg-zinc-700" />
                  </div>
                )}

                <div className="space-y-3">
                  {daySessions.map((session) => (
                    <div key={session.id} className="rounded-xl bg-zinc-900 p-4">
                      {/* Session header */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="text-white font-semibold">
                          Сессия #{session.id.slice(0, 8)}
                        </div>
                        <div className="text-xs text-zinc-400">
                          {formatTime(session.created_at)} - {formatTime(session.closed_at)}
                        </div>
                      </div>

                      {/* Session details */}
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between text-zinc-300">
                          <span>Стол:</span>
                          <span className="text-white">{session.table_name}</span>
                        </div>

                        {/* Show dealer assignments with rake */}
                        {session.dealer_assignments && session.dealer_assignments.length > 0 ? (
                          <div className="text-zinc-300">
                            <span>{session.dealer_assignments.length > 1 ? "Дилеры:" : "Дилер:"}</span>
                            <div className="mt-2 space-y-2">
                              {session.dealer_assignments.map((assignment) => (
                                <div key={assignment.id} className="bg-zinc-800/50 rounded-lg px-3 py-2">
                                  <div className="flex justify-between items-center">
                                    <span className="text-white font-medium">{assignment.dealer_username}</span>
                                    <span className={`font-semibold ${(assignment.rake ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                                      {formatMoney(assignment.rake ?? 0)}
                                    </span>
                                  </div>
                                  <div className="text-xs text-zinc-500 mt-1">
                                    {formatTime(assignment.started_at)}
                                    {assignment.ended_at ? ` — ${formatTime(assignment.ended_at)}` : " — ..."}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : session.dealer_username && (
                          <div className="flex justify-between text-zinc-300">
                            <span>Дилер:</span>
                            <span className="text-white">{session.dealer_username}</span>
                          </div>
                        )}

                        {session.waiter_username && (
                          <div className="flex justify-between text-zinc-300">
                            <span>Официант:</span>
                            <span className="text-white">{session.waiter_username}</span>
                          </div>
                        )}

                        <div className="flex justify-between text-zinc-300">
                          <span>Фишки в игре:</span>
                          <span className="text-white">{formatMoney(session.chips_in_play ?? 0)}</span>
                        </div>

                        <div className="flex justify-between text-zinc-300">
                          <span>Всего покупок:</span>
                          <span className="text-white">{formatMoney(session.total_buyins)}</span>
                        </div>

                        <div className="flex justify-between text-zinc-300">
                          <span>Всего выплат:</span>
                          <span className="text-white">{formatMoney(Math.abs(session.total_cashouts))}</span>
                        </div>

                        <div className="flex justify-between text-zinc-300">
                          <span>Рейк:</span>
                          <span className="text-white font-semibold">{formatMoney(session.total_rake)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </main>
    </RequireAuth>
  );
}
