"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import TopMenu from "@/components/TopMenu";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import { apiFetch } from "@/lib/api";
import { formatMoney, formatTime, formatDateTime } from "@/lib/utils";
import type { Table } from "@/lib/types";

type DealerRakeEntry = {
  id: number;
  amount: number;
  created_at: string;
  created_by_username: string | null;
};

type SessionDealerAssignment = {
  id: number;
  dealer_id: number;
  dealer_username: string;
  started_at: string;
  ended_at: string | null;
  rake: number | null;
  rake_entries: DealerRakeEntry[];
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

type OngoingSession = {
  id: string;
  table_id: number;
  date: string;
  status: string;
  created_at: string;
  chips_in_play: number | null;
  dealer_assignments: SessionDealerAssignment[];
};

type SessionRakeInfo = {
  total_rake: number;
  total_buyins: number;
  total_cashouts: number;
  chips_on_table: number;
  total_credit: number;
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
  const [ongoingSession, setOngoingSession] = useState<OngoingSession | null>(null);
  const [ongoingRakeInfo, setOngoingRakeInfo] = useState<SessionRakeInfo | null>(null);
  const [tables, setTables] = useState<Table[]>([]);
  const [selectedTableId, setSelectedTableId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rakeHistoryModal, setRakeHistoryModal] = useState<{
    dealerName: string;
    rakeEntries: DealerRakeEntry[];
    totalRake: number;
  } | null>(null);
  const [seatsHistoryModal, setSeatsHistoryModal] = useState<{
    sessionId: string;
    sessionLabel: string;
  } | null>(null);
  const [seatsHistory, setSeatsHistory] = useState<Array<{
    seat_no: number;
    player_name: string | null;
    entries: Array<{
      type: string;
      created_at: string;
      old_name?: string | null;
      new_name?: string | null;
      amount?: number | null;
      payment_type?: string | null;
      created_by_username?: string | null;
    }>;
  }>>([]);
  const [seatsHistoryLoading, setSeatsHistoryLoading] = useState(false);

  const loadTables = useCallback(async () => {
    try {
      const res = await apiFetch("/api/admin/tables");
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка загрузки столов");
      }
      const tablesData = await res.json();
      setTables(tablesData);
      return tablesData;
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка загрузки столов");
      return [];
    }
  }, []);

  const loadSessions = useCallback(async () => {
    if (!selectedTableId) return;

    setLoading(true);
    setError(null);
    try {
      // Load closed sessions
      const closedRes = await apiFetch(`/api/admin/closed-sessions?table_id=${selectedTableId}`);
      if (!closedRes.ok) {
        const err = await closedRes.json().catch(() => ({}));
        throw new Error(err.detail || "Ошибка загрузки сессий");
      }
      setSessions(await closedRes.json());

      // Load ongoing session
      const openRes = await apiFetch(`/api/sessions/open?table_id=${selectedTableId}`);
      if (openRes.ok) {
        const openSession = await openRes.json();
        if (openSession) {
          setOngoingSession(openSession);
          // Load rake info for ongoing session
          const rakeRes = await apiFetch(`/api/sessions/${openSession.id}/rake`);
          if (rakeRes.ok) {
            setOngoingRakeInfo(await rakeRes.json());
          }
        } else {
          setOngoingSession(null);
          setOngoingRakeInfo(null);
        }
      } else {
        setOngoingSession(null);
        setOngoingRakeInfo(null);
      }
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Ошибка");
    } finally {
      setLoading(false);
    }
  }, [selectedTableId]);

  const loadSeatsHistory = useCallback(async (sessionId: string, sessionLabel: string) => {
    setSeatsHistoryModal({ sessionId, sessionLabel });
    setSeatsHistoryLoading(true);
    try {
      const res = await apiFetch(`/api/sessions/${sessionId}/seats-history`);
      if (res.ok) {
        setSeatsHistory(await res.json());
      } else {
        setSeatsHistory([]);
      }
    } catch {
      setSeatsHistory([]);
    } finally {
      setSeatsHistoryLoading(false);
    }
  }, []);

  // Load tables on mount and auto-select table
  useEffect(() => {
    if (user && (user.role === "superadmin" || user.role === "table_admin")) {
      loadTables().then((tablesData: Table[]) => {
        // Auto-select first table (for table_admin, API returns only their table)
        if (tablesData.length > 0) {
          setSelectedTableId(tablesData[0].id);
        }
      });
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

          {!loading && selectedTableId && sessions.length === 0 && !ongoingSession && (
            <div className="rounded-xl bg-zinc-900 text-white/70 px-3 py-3 text-sm rounded-xl">
              Нет сессий
            </div>
          )}

          {/* Ongoing session */}
          {!loading && selectedTableId && ongoingSession && (
            <div className="rounded-xl bg-gradient-to-br from-green-900/30 to-zinc-900 border border-green-700/50 p-4">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                <div className="text-white font-semibold">Текущая сессия</div>
              </div>
              <div className="text-xs text-zinc-400 mb-3">
                Начало: {formatTime(ongoingSession.created_at)}
              </div>

              {/* Dealer assignments */}
              {ongoingSession.dealer_assignments && ongoingSession.dealer_assignments.length > 0 && (
                <div className="text-zinc-300 mb-3">
                  <span>{ongoingSession.dealer_assignments.length > 1 ? "Дилеры:" : "Дилер:"}</span>
                  <div className="mt-2 space-y-2">
                    {ongoingSession.dealer_assignments.map((assignment) => {
                      const manualRake = (assignment.rake_entries || []).reduce((sum, e) => sum + e.amount, 0);
                      const hasRakeEntries = (assignment.rake_entries || []).length > 0;
                      return (
                        <button
                          key={assignment.id}
                          className="w-full bg-zinc-800/50 rounded-lg px-3 py-2 text-left hover:bg-zinc-700/50 transition-colors cursor-pointer"
                          onClick={() => setRakeHistoryModal({
                            dealerName: assignment.dealer_username,
                            rakeEntries: assignment.rake_entries || [],
                            totalRake: manualRake,
                          })}
                        >
                          <div className="flex justify-between items-center">
                            <span className="text-white font-medium">{assignment.dealer_username}</span>
                            <span className={`font-semibold ${manualRake >= 0 ? "text-green-400" : "text-red-400"}`}>
                              {formatMoney(manualRake)}
                              {hasRakeEntries && <span className="text-xs text-zinc-400 ml-1">({assignment.rake_entries.length})</span>}
                            </span>
                          </div>
                          <div className="text-xs text-zinc-500 mt-1">
                            {formatTime(assignment.started_at)}
                            {assignment.ended_at ? ` — ${formatTime(assignment.ended_at)}` : " — ..."}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Chips in play and credits */}
              <div className="space-y-2 text-sm">
                <div className="flex justify-between text-zinc-300">
                  <span>Фишки в игре:</span>
                  <span className="text-white font-semibold">
                    {formatMoney(ongoingRakeInfo?.chips_on_table ?? ongoingSession.chips_in_play ?? 0)}
                  </span>
                </div>
                {ongoingRakeInfo && ongoingRakeInfo.total_credit > 0 && (
                  <div className="flex justify-between text-zinc-300">
                    <span className="text-amber-400">В кредит:</span>
                    <span className="text-amber-400 font-semibold">
                      {formatMoney(ongoingRakeInfo.total_credit)}
                    </span>
                  </div>
                )}
                <div className="flex justify-between text-zinc-300">
                  <span>Рейк:</span>
                  <span className="text-white font-semibold">
                    {formatMoney(
                      (ongoingSession.dealer_assignments || []).reduce(
                        (sum, a) => sum + (a.rake_entries || []).reduce((s, e) => s + e.amount, 0),
                        0
                      )
                    )}
                  </span>
                </div>
              </div>

              {/* Seats history button */}
              <button
                className="mt-3 w-full rounded-xl bg-zinc-800 text-zinc-300 py-2 text-sm hover:bg-zinc-700"
                onClick={() => loadSeatsHistory(ongoingSession.id, "Текущая сессия")}
              >
                История мест
              </button>
            </div>
          )}

          {/* Closed sessions header */}
          {!loading && selectedTableId && sessions.length > 0 && (
            <div className="text-zinc-400 text-sm mt-4 mb-2">Закрытые сессии</div>
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
                              {session.dealer_assignments.map((assignment) => {
                                const manualRake = (assignment.rake_entries || []).reduce((sum, e) => sum + e.amount, 0);
                                const hasRakeEntries = (assignment.rake_entries || []).length > 0;
                                return (
                                  <button
                                    key={assignment.id}
                                    className="w-full bg-zinc-800/50 rounded-lg px-3 py-2 text-left hover:bg-zinc-700/50 transition-colors cursor-pointer"
                                    onClick={() => setRakeHistoryModal({
                                      dealerName: assignment.dealer_username,
                                      rakeEntries: assignment.rake_entries || [],
                                      totalRake: manualRake,
                                    })}
                                  >
                                    <div className="flex justify-between items-center">
                                      <span className="text-white font-medium">{assignment.dealer_username}</span>
                                      <span className={`font-semibold ${manualRake >= 0 ? "text-green-400" : "text-red-400"}`}>
                                        {formatMoney(manualRake)}
                                        {hasRakeEntries && <span className="text-xs text-zinc-400 ml-1">({assignment.rake_entries.length})</span>}
                                      </span>
                                    </div>
                                    <div className="text-xs text-zinc-500 mt-1">
                                      {formatTime(assignment.started_at)}
                                      {assignment.ended_at ? ` — ${formatTime(assignment.ended_at)}` : " — ..."}
                                    </div>
                                  </button>
                                );
                              })}
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
                          <span>Рейк:</span>
                          <span className="text-white font-semibold">
                            {formatMoney(
                              (session.dealer_assignments || []).reduce(
                                (sum, a) => sum + (a.rake_entries || []).reduce((s, e) => s + e.amount, 0),
                                0
                              )
                            )}
                          </span>
                        </div>

                        {/* Seats history button */}
                        <button
                          className="mt-2 w-full rounded-xl bg-zinc-800 text-zinc-300 py-2 text-sm hover:bg-zinc-700"
                          onClick={() => loadSeatsHistory(session.id, `Сессия #${session.id.slice(0, 8)}`)}
                        >
                          История мест
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Rake History Fullscreen Overlay */}
        {rakeHistoryModal && (
          <div className="fixed inset-0 z-50 bg-zinc-900 flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-zinc-700">
              <div className="text-lg font-bold text-white">
                История рейка: {rakeHistoryModal.dealerName}
              </div>
              <button
                className="text-zinc-400 px-3 py-2 hover:text-white"
                onClick={() => setRakeHistoryModal(null)}
              >
                Закрыть
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {rakeHistoryModal.rakeEntries.length === 0 ? (
                <div className="text-center text-zinc-500 py-8">Нет записей рейка</div>
              ) : (
                <div className="space-y-3">
                  {rakeHistoryModal.rakeEntries.map((entry) => (
                    <div
                      key={entry.id}
                      className="rounded-xl bg-zinc-800 border border-zinc-700 p-3"
                    >
                      <div className="flex justify-between items-center">
                        <span className="text-green-400 font-semibold text-lg">
                          +{formatMoney(entry.amount)}
                        </span>
                        <span className="text-xs text-zinc-500">
                          {formatDateTime(entry.created_at)}
                        </span>
                      </div>
                      {entry.created_by_username && (
                        <div className="text-xs text-zinc-500 mt-1">
                          Добавил: {entry.created_by_username}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="p-4 border-t border-zinc-700 bg-zinc-800">
              <div className="flex justify-between items-center mb-4">
                <span className="text-zinc-300">Итого:</span>
                <span className="text-green-400 font-bold text-xl">
                  {formatMoney(rakeHistoryModal.totalRake)}
                </span>
              </div>
              <button
                className="w-full rounded-xl bg-zinc-700 text-white py-3 hover:bg-zinc-600"
                onClick={() => setRakeHistoryModal(null)}
              >
                Закрыть
              </button>
            </div>
          </div>
        )}

        {/* Seats History Fullscreen Overlay */}
        {seatsHistoryModal && (
          <div className="fixed inset-0 z-50 bg-zinc-900 flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-zinc-700">
              <div className="text-lg font-bold text-white">
                История мест: {seatsHistoryModal.sessionLabel}
              </div>
              <button
                className="text-zinc-400 px-3 py-2 hover:text-white"
                onClick={() => {
                  setSeatsHistoryModal(null);
                  setSeatsHistory([]);
                }}
              >
                Закрыть
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {seatsHistoryLoading ? (
                <div className="text-center text-zinc-500 py-8">Загрузка...</div>
              ) : seatsHistory.length === 0 ? (
                <div className="text-center text-zinc-500 py-8">Нет данных</div>
              ) : (
                <div className="space-y-6">
                  {seatsHistory.map((seat) => (
                    <div
                      key={seat.seat_no}
                      className="rounded-xl bg-zinc-800 border border-zinc-700 overflow-hidden"
                    >
                      {/* Seat header */}
                      <div className="bg-zinc-700/50 px-4 py-3 border-b border-zinc-600">
                        <div className="flex items-center justify-between">
                          <span className="text-white font-bold">Место #{seat.seat_no}</span>
                          {seat.player_name && (
                            <span className="text-zinc-300 text-sm">{seat.player_name}</span>
                          )}
                        </div>
                      </div>

                      {/* Seat entries */}
                      <div className="p-3">
                        {seat.entries.length === 0 ? (
                          <div className="text-zinc-500 text-sm text-center py-2">Нет записей</div>
                        ) : (
                          <div className="space-y-2">
                            {seat.entries.map((entry, idx) => (
                              <div
                                key={idx}
                                className="rounded-lg bg-zinc-900 px-3 py-2"
                              >
                                <div className="flex items-center justify-between text-xs text-zinc-500 mb-1">
                                  <span>
                                    {new Date(entry.created_at).toLocaleString("ru-RU", {
                                      day: "2-digit",
                                      month: "2-digit",
                                      hour: "2-digit",
                                      minute: "2-digit",
                                    })}
                                  </span>
                                  {entry.created_by_username && (
                                    <span>{entry.created_by_username}</span>
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
                                      {formatMoney(entry.amount ?? 0)}
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
                  ))}
                </div>
              )}
            </div>

            <div className="p-4 border-t border-zinc-700 bg-zinc-800">
              <button
                className="w-full rounded-xl bg-zinc-700 text-white py-3 hover:bg-zinc-600"
                onClick={() => {
                  setSeatsHistoryModal(null);
                  setSeatsHistory([]);
                }}
              >
                Закрыть
              </button>
            </div>
          </div>
        )}
      </main>
    </RequireAuth>
  );
}
