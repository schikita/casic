"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import SeatGrid from "@/components/SeatGrid";
import SeatActionSheet from "@/components/SeatActionSheet";
import StartSessionModal from "@/components/StartSessionModal";
import CashConfirmationModal from "@/components/CashConfirmationModal";
import SessionCloseConfirmationModal from "@/components/SessionCloseConfirmationModal";
import ReplaceDealerModal from "@/components/ReplaceDealerModal";
import AddDealerModal from "@/components/AddDealerModal";
import RemoveDealerModal from "@/components/RemoveDealerModal";
import DealerRakeModal from "@/components/DealerRakeModal";
import TopMenu from "@/components/TopMenu";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import { apiJson, getSelectedTableId, setSelectedTableId } from "@/lib/api";
import { normalizeTableId, getErrorMessage, formatTime, calculateEarnings, formatMoney } from "@/lib/utils";
import type { Seat, Session, Table, SessionDealerAssignment, DealerRakeEntry } from "@/lib/types";

function buildOpenSessionUrl(userRole: string | undefined, tableId?: number): string {
  let url = "/api/sessions/open";
  // Only add table_id for superadmin and table_admin, not for dealers
  if ((userRole === "superadmin" || userRole === "table_admin") && tableId) {
    url += "?table_id=" + tableId;
  }
  return url;
}

export default function HomePage() {
  const { user } = useAuth();

  const [tables, setTables] = useState<Table[]>([]);
  const [tableId, setTableId] = useState<number | null>(null);

  const [session, setSession] = useState<Session | null>(null);
  const [seats, setSeats] = useState<Seat[]>([]);
  const [activeSeatNo, setActiveSeatNo] = useState<number | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showStartModal, setShowStartModal] = useState<boolean>(false);
  const [showCashModal, setShowCashModal] = useState<boolean>(false);
  const [pendingChipAmount, setPendingChipAmount] = useState<number | null>(null);
  const [showCloseModal, setShowCloseModal] = useState<boolean>(false);
  const [creditAmount, setCreditAmount] = useState<number>(0);
  const [creditByPlayer, setCreditByPlayer] = useState<Array<{ seat_no: number; player_name: string | null; amount: number }>>([]);
  const [showReplaceDealerModal, setShowReplaceDealerModal] = useState<boolean>(false);
  const [showAddDealerModal, setShowAddDealerModal] = useState<boolean>(false);
  const [removeDealerInfo, setRemoveDealerInfo] = useState<{ assignmentId: number; dealerName: string } | null>(null);
  const [rakeModalInfo, setRakeModalInfo] = useState<{ assignmentId: number; dealerName: string; currentRake: number } | null>(null);
  const [showDealerHistory, setShowDealerHistory] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"table" | "dealers">("table");
  const [rake, setRake] = useState<{ total_rake: number; total_buyins: number; total_cashouts: number; total_credit: number } | null>(null);
  const [rakeLogInfo, setRakeLogInfo] = useState<{ dealerName: string; entries: DealerRakeEntry[] } | null>(null);

  // Roles allowed to start sessions
  const canStartSession =
    user?.role === "superadmin" ||
    user?.role === "table_admin";

  const activeSeat = useMemo(() => {
    if (!activeSeatNo) return null;
    return seats.find((s) => s.seat_no === activeSeatNo) ?? null;
  }, [activeSeatNo, seats]);

  const activeTable = useMemo(() => {
    if (!tableId) return null;
    return tables.find((t) => t.id === tableId) ?? null;
  }, [tables, tableId]);

  const loadTablesAndSelect = useCallback(async () => {
    if (!user) return;

    setError(null);

    try {
      // Superadmin and table_admin can select from multiple tables
      if (user.role === "superadmin" || user.role === "table_admin") {
        const list = await apiJson<Table[]>("/api/admin/tables");
        setTables(list);

        const stored = getSelectedTableId();
        const preferred =
          stored && list.some((t) => t.id === stored)
            ? stored
            : list[0]?.id ?? null;

        setTableId(preferred);
        if (preferred) setSelectedTableId(preferred);

        if (!preferred) {
          setSession(null);
          setSeats([]);
          setLoading(false);
        }

        return;
      }

      // For dealer/waiter, use their assigned table from user context
      const tid = normalizeTableId(user.table_id);
      setTableId(tid);

      if (!tid) {
        setSession(null);
        setSeats([]);
        setLoading(false);
      }
    } catch (e) {
      setTables([]);
      setTableId(null);
      setSession(null);
      setSeats([]);
      setLoading(false);
      setError(getErrorMessage(e) ?? "Ошибка загрузки столов");
    }
  }, [user]);

  const loadOpenSession = useCallback(async (tid?: number) => {
    setError(null);
    setLoading(true);
    try {
      const url = buildOpenSessionUrl(user?.role, tid);
      const s = await apiJson<Session | null>(url);
      setSession(s);

      if (s) {
        const [list, rakeData] = await Promise.all([
          apiJson<Seat[]>("/api/sessions/" + s.id + "/seats"),
          apiJson<{ total_rake: number; total_buyins: number; total_cashouts: number; total_credit: number }>("/api/sessions/" + s.id + "/rake"),
        ]);
        setSeats(list);
        setRake(rakeData);
      } else {
        setSeats([]);
        setRake(null);
      }
    } catch (e) {
      setError(getErrorMessage(e) || "Ошибка");
    } finally {
      setLoading(false);
    }
  }, [user]);

  const handleSessionCreated = useCallback(() => {
    setShowStartModal(false);
    if (tableId) {
      loadOpenSession(tableId);
    }
  }, [tableId, loadOpenSession]);

  const updateSeatInState = useCallback((updated: Seat) => {
    setSeats((prev) =>
      prev.map((s) => (s.seat_no === updated.seat_no ? updated : s))
    );
  }, []);

  const assignPlayer = useCallback(async (playerName: string | null, skipHistory: boolean = false) => {
    if (!session || !activeSeatNo) return;
    setError(null);
    setBusy(true);
    try {
      const url = "/api/sessions/" + session.id + "/seats/" + activeSeatNo + (skipHistory ? "?skip_history=true" : "");
      const updated = await apiJson<Seat>(url, {
        method: "PUT",
        body: JSON.stringify({ player_name: playerName }),
      });
      updateSeatInState(updated);
    } catch (e) {
      setError(getErrorMessage(e) || "Ошибка");
    } finally {
      setBusy(false);
    }
  }, [session, activeSeatNo, updateSeatInState]);

  const clearSeat = useCallback(async () => {
    if (!session || !activeSeatNo) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await apiJson<Seat>(
        "/api/sessions/" + session.id + "/seats/" + activeSeatNo + "/clear",
        { method: "POST" }
      );
      updateSeatInState(updated);
    } catch (e) {
      setError(getErrorMessage(e) || "Ошибка");
    } finally {
      setBusy(false);
    }
  }, [session, activeSeatNo, updateSeatInState]);

  const confirmChipPurchase = useCallback(async (amount: number, paymentType: "cash" | "credit") => {
    if (!session || !activeSeatNo) return;
    setError(null);
    setBusy(true);
    try {
      const body: {
        seat_no: number;
        amount: number;
        payment_type?: "cash" | "credit";
      } = {
        seat_no: activeSeatNo,
        amount: amount,
      };

      // Only include payment_type for positive amounts (buyin)
      if (amount > 0) {
        body.payment_type = paymentType;
      }

      const updated = await apiJson<Seat>(
        "/api/sessions/" + session.id + "/chips",
        {
          method: "POST",
          body: JSON.stringify(body),
        }
      );
      updateSeatInState(updated);

      // Refresh session and rake to get updated data
      const url = buildOpenSessionUrl(user?.role, session.table_id);
      const [updatedSession, rakeData] = await Promise.all([
        apiJson<Session>(url),
        apiJson<{ total_rake: number; total_buyins: number; total_cashouts: number; total_credit: number }>("/api/sessions/" + session.id + "/rake"),
      ]);
      if (updatedSession) {
        setSession(updatedSession);
      }
      setRake(rakeData);

      setShowCashModal(false);
      setPendingChipAmount(null);
      setActiveSeatNo(null); // Close the SeatActionSheet
    } catch (e) {
      setError(getErrorMessage(e) || "Ошибка");
    } finally {
      setBusy(false);
    }
  }, [session, activeSeatNo, updateSeatInState, user]);

  const addChips = useCallback((amount: number) => {
    if (!session || !activeSeatNo) return;
    setError(null);

    // Only show cash/credit modal for positive amounts (buyin)
    // Negative amounts (cashout) are processed directly
    if (amount > 0) {
      setPendingChipAmount(amount);
      setShowCashModal(true);
    } else {
      // For cashout, process directly without payment type
      confirmChipPurchase(amount, "cash");
    }
  }, [session, activeSeatNo, confirmChipPurchase]);

  const showCloseConfirmation = useCallback(async () => {
    if (!session) return;
    setError(null);
    setBusy(true);
    try {
      const result = await apiJson<{
        total_credit: number;
        credit_by_player: Array<{ seat_no: number; player_name: string | null; amount: number }>;
      }>(
        "/api/sessions/" + session.id + "/non-cash-purchases"
      );
      setCreditAmount(result.total_credit);
      setCreditByPlayer(result.credit_by_player);
      setShowCloseModal(true);
    } catch (e) {
      setError(getErrorMessage(e) || "Ошибка");
    } finally {
      setBusy(false);
    }
  }, [session]);

  const confirmCloseSession = useCallback(async () => {
    if (!session) return;
    setError(null);
    setBusy(true);
    try {
      await apiJson<Session>(
        "/api/sessions/" + session.id + "/close",
        {
          method: "POST",
          body: JSON.stringify({ dealer_rakes: [] }),
        }
      );
      setSession(null);
      setSeats([]);
      setShowCloseModal(false);
    } catch (e) {
      setError(getErrorMessage(e) || "Ошибка");
    } finally {
      setBusy(false);
    }
  }, [session]);

  const handleRemoveDealer = useCallback((assignmentId: number, dealerName: string) => {
    if (!session || !tableId) return;
    setRemoveDealerInfo({ assignmentId, dealerName });
  }, [session, tableId]);

  useEffect(() => {
    if (!user) return;
    loadTablesAndSelect();
  }, [user, loadTablesAndSelect]);

  useEffect(() => {
    if (!tableId) return;
    loadOpenSession(tableId);
  }, [tableId, loadOpenSession]);

  const totals = useMemo(() => {
    const chips = seats.reduce((acc, s) => acc + (s.total_chips_played || 0), 0);
    return { chips };
  }, [seats]);

  // Calculate current dealer earnings based on their assignment
  const dealerEarnings = useMemo(() => {
    if (!session?.dealer || !session.dealer.hourly_rate) {
      return 0;
    }

    // Find the current dealer's active assignment (the one without ended_at)
    const currentAssignment = session.dealer_assignments?.find(
      (a) => a.dealer_id === session.dealer?.id && !a.ended_at
    );

    if (currentAssignment) {
      // Calculate earnings from the assignment start time to now
      return calculateEarnings(
        session.dealer.hourly_rate,
        currentAssignment.started_at,
        null
      );
    }

    // Fallback: if no assignment found, calculate from session start
    // (this shouldn't happen in normal operation)
    return calculateEarnings(
      session.dealer.hourly_rate,
      session.created_at,
      null
    );
  }, [session]);

  // Calculate waiter earnings from session start to now
  const waiterEarnings = useMemo(() => {
    if (!session?.waiter || !session.waiter.hourly_rate) {
      return 0;
    }

    // Waiters work the entire session
    return calculateEarnings(
      session.waiter.hourly_rate,
      session.created_at,
      null
    );
  }, [session]);

  return (
    <RequireAuth>
      <main className="p-3 max-w-md mx-auto">
        <TopMenu />

        <div className="flex items-center justify-between mb-3 gap-3">
          {session && (
            <div className="rounded-xl bg-zinc-900 text-white px-3 py-3 flex-shrink-0 flex items-center gap-2">
              <span className="text-xs text-zinc-300">Фишек на столе:</span>
              <span className="text-base font-bold tabular-nums">{totals.chips}</span>
            </div>
          )}

          {(user?.role === "superadmin" || user?.role === "table_admin") && tables.length > 0 && (
            <select
              className="rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-zinc-500 flex-1 min-w-0"
              value={tableId ?? ""}
              onChange={(e) => {
                const id = Number(e.target.value);
                setTableId(id);
                setSelectedTableId(id);
              }}
            >
              <option value="" disabled>
                Выберите стол
              </option>
              {tables.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          )}
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-900/50 text-red-200 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {loading && (
          <div className="rounded-xl bg-zinc-800 px-3 py-3 text-sm text-zinc-400 border border-zinc-700">
            Загрузка…
          </div>
        )}

        {!loading && !tableId && (
          <div className="rounded-xl bg-zinc-800 text-zinc-400 px-3 py-3 text-sm border border-zinc-700">
            {(user?.role === "superadmin" || user?.role === "table_admin")
              ? "Нет созданных столов. Создайте стол в админке."
              : "Нет доступного стола. Сессия не активна для этого дилера/официанта."}
          </div>
        )}

        {!loading && tableId && !session && (
          <>
            {canStartSession ? (
              <button
                className="w-full rounded-xl bg-green-600 text-white py-4 font-bold text-lg active:bg-green-700 disabled:opacity-60 hover:bg-green-700/90"
                onClick={() => setShowStartModal(true)}
                disabled={busy}
              >
                Открыть сессию
              </button>
            ) : (
              <div className="rounded-xl bg-zinc-800 px-3 py-3 text-sm text-zinc-400 border border-zinc-700">
                Сессия не открыта. Обратитесь к администратору стола для открытия сессии.
              </div>
            )}

            <StartSessionModal
              open={showStartModal}
              tableId={tableId}
              seatsCount={activeTable?.seats_count ?? 24}
              onClose={() => setShowStartModal(false)}
              onSessionCreated={handleSessionCreated}
            />
          </>
        )}



        {!loading && session && (
          <>
            {/* Tabs */}
            <div className="mb-3 grid grid-cols-2 gap-2">
              <button
                className={`rounded-xl py-2 text-sm font-semibold border ${activeTab === "table" ? "bg-white text-zinc-900 border-white" : "bg-zinc-800 text-zinc-300 border-zinc-700"}`}
                onClick={() => setActiveTab("table")}
                disabled={busy}
              >
                Стол
              </button>
              <button
                className={`rounded-xl py-2 text-sm font-semibold border ${activeTab === "dealers" ? "bg-white text-zinc-900 border-white" : "bg-zinc-800 text-zinc-300 border-zinc-700"}`}
                onClick={() => setActiveTab("dealers")}
                disabled={busy}
              >
                Дилеры
              </button>
            </div>

            {/* Dealers tab content */}
            {activeTab === "dealers" && (
              <div className="mb-3 rounded-xl bg-zinc-800 p-4 border border-zinc-700">
                {/* Summary Totals - FIRST */}
                <div className="mb-4 rounded-lg bg-zinc-700 text-white p-3">
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <span className="text-zinc-400">Всего рейк:</span>
                      <div className="text-lg font-bold tabular-nums">
                        {formatMoney((session.dealer_assignments ?? []).reduce((sum, a) => sum + (a.rake ?? 0), 0))}
                      </div>
                    </div>
                    <div>
                      <span className="text-zinc-400">Всего часов:</span>
                      <div className="text-lg font-bold tabular-nums">
                        {(() => {
                          const totalHours = (session.dealer_assignments ?? []).reduce((sum, a) => {
                            const startStr = a.started_at.endsWith('Z') ? a.started_at : a.started_at + 'Z';
                            const start = new Date(startStr);
                            const end = a.ended_at
                              ? new Date(a.ended_at.endsWith('Z') ? a.ended_at : a.ended_at + 'Z')
                              : new Date();
                            return sum + (end.getTime() - start.getTime()) / (1000 * 60 * 60);
                          }, 0);
                          return totalHours.toFixed(1) + " ч";
                        })()}
                      </div>
                    </div>
                    <div>
                      <span className="text-zinc-400">Всего ЗП:</span>
                      <div className="text-lg font-bold tabular-nums">
                        {formatMoney(
                          [...new Set((session.dealer_assignments ?? []).map(a => a.dealer_username))].reduce((sum, name) => {
                            const assignments = (session.dealer_assignments ?? []).filter(a => a.dealer_username === name);
                            const totalHours = assignments.reduce((s, a) => {
                              const startStr = a.started_at.endsWith('Z') ? a.started_at : a.started_at + 'Z';
                              const start = new Date(startStr);
                              const end = a.ended_at
                                ? new Date(a.ended_at.endsWith('Z') ? a.ended_at : a.ended_at + 'Z')
                                : new Date();
                              return s + (end.getTime() - start.getTime()) / (1000 * 60 * 60);
                            }, 0);
                            const hourlyRate = assignments[0]?.dealer_hourly_rate || 0;
                            return sum + Math.round(totalHours * hourlyRate);
                          }, 0)
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Active Dealers Section - SECOND */}
                <div className="mb-4">
                  <div className="text-sm font-semibold text-white mb-2">Активные дилеры</div>
                  {session.dealer_assignments && session.dealer_assignments.filter((a) => !a.ended_at).length > 0 ? (
                    <div className="space-y-2">
                      {(() => {
                        const activeDealers = session.dealer_assignments.filter((assignment) => !assignment.ended_at);
                        const hasMultipleDealers = activeDealers.length > 1;

                        return activeDealers.map((assignment) => {
                          const earnings = assignment.dealer_hourly_rate
                            ? calculateEarnings(assignment.dealer_hourly_rate, assignment.started_at, null)
                            : 0;

                          return (
                            <div key={assignment.id} className="rounded-lg bg-zinc-700 p-2 border border-zinc-600">
                              <div className="flex items-start justify-between">
                                <div className="flex-1">
                                  <div className="text-sm font-semibold text-white">{assignment.dealer_username}</div>
                                  <div className="text-xs text-zinc-400">Начал: {formatTime(assignment.started_at)}</div>
                                  {assignment.dealer_hourly_rate && earnings > 0 && (
                                    <div className="text-xs text-zinc-400 mt-1">
                                      Заработано:{" "}
                                      <span className="font-semibold text-green-400">{formatMoney(earnings)}</span>
                                    </div>
                                  )}
                                  {assignment.rake != null && assignment.rake > 0 && (
                                    <button
                                      className="text-xs text-zinc-400 mt-1 text-left hover:bg-zinc-600 rounded px-1 -mx-1"
                                      onClick={() => setRakeLogInfo({ dealerName: assignment.dealer_username, entries: assignment.rake_entries || [] })}
                                    >
                                      Рейк:{" "}
                                      <span className="font-semibold text-amber-400 underline">{formatMoney(assignment.rake)}</span>
                                    </button>
                                  )}
                                </div>
                                <div className="flex flex-col gap-1">
                                  <button
                                    className="rounded-lg bg-amber-500 text-white px-3 py-1 text-xs active:bg-amber-600 disabled:opacity-50"
                                    onClick={() => setRakeModalInfo({ assignmentId: assignment.id, dealerName: assignment.dealer_username, currentRake: assignment.rake ?? 0 })}
                                    disabled={busy}
                                  >
                                    Рейк
                                  </button>
                                  {(user?.role === "superadmin" || user?.role === "table_admin") && hasMultipleDealers && (
                                    <button
                                      className="rounded-lg bg-red-600 text-white px-3 py-1 text-xs active:bg-red-700 disabled:opacity-50"
                                      onClick={() => handleRemoveDealer(assignment.id, assignment.dealer_username)}
                                      disabled={busy}
                                    >
                                      Завершить
                                    </button>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  ) : (
                    <div className="text-sm text-zinc-500">Нет активных дилеров</div>
                  )}
                </div>

                {/* Waiter Section - THIRD */}
                {session.waiter && (
                  <div className="mb-4">
                    <div className="text-sm font-semibold text-white mb-2">Официант</div>
                    <div className="rounded-lg bg-zinc-700 p-2 border border-zinc-600">
                      <div className="text-sm font-semibold text-white">{session.waiter.username}</div>
                      <div className="text-xs text-zinc-400">Начал: {formatTime(session.created_at)}</div>
                      {session.waiter.hourly_rate && waiterEarnings > 0 && (
                        <div className="text-xs text-zinc-400 mt-1">
                          Заработано:{" "}
                          <span className="font-semibold text-green-400">{formatMoney(waiterEarnings)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Separator between waiter and session dealers */}
                {session.dealer_assignments && session.dealer_assignments.length > 0 && (
                  <div className="border-t-2 border-zinc-600 my-4" />
                )}

                {/* Mobile-friendly dealer cards - Dealers per session - FOURTH */}
                {session.dealer_assignments && session.dealer_assignments.length > 0 && (
                  <div>
                    <div className="text-sm font-semibold text-white mb-2">Дилеры за сессию</div>
                    <div className="space-y-2">
                      {(() => {
                        // Group assignments by dealer
                        const dealerNames = [...new Set(session.dealer_assignments.map(a => a.dealer_username))];
                        return dealerNames.map((name) => {
                          const assignments = session.dealer_assignments!.filter(a => a.dealer_username === name);
                          const totalHours = assignments.reduce((sum, a) => {
                            const startStr = a.started_at.endsWith('Z') ? a.started_at : a.started_at + 'Z';
                            const start = new Date(startStr);
                            const end = a.ended_at
                              ? new Date(a.ended_at.endsWith('Z') ? a.ended_at : a.ended_at + 'Z')
                              : new Date();
                            const hours = (end.getTime() - start.getTime()) / (1000 * 60 * 60);
                            return sum + hours;
                          }, 0);
                          const hourlyRate = assignments[0]?.dealer_hourly_rate || 0;
                          const salary = Math.round(totalHours * hourlyRate);
                          const totalRake = assignments.reduce((sum, a) => sum + (a.rake ?? 0), 0);
                          const isActive = assignments.some(a => !a.ended_at);

                          return (
                            <div key={name} className={`rounded-lg p-3 border ${isActive ? 'border-green-500 bg-zinc-700' : 'border-zinc-600 bg-zinc-700'}`}>
                              <div className="flex items-center justify-between mb-2">
                                <div className="text-sm font-semibold text-white">{name}</div>
                                {isActive && (
                                  <span className="text-xs bg-green-500 text-white px-2 py-0.5 rounded-full">Активен</span>
                                )}
                              </div>
                              <div className="grid grid-cols-2 gap-2 text-xs">
                                <div>
                                  <span className="text-zinc-500">Время:</span>
                                  <div className="text-zinc-300">
                                    {assignments.map((a) => (
                                      <div key={a.id}>
                                        {formatTime(a.started_at)}–{a.ended_at ? formatTime(a.ended_at) : "…"}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-zinc-500">Часы:</span>
                                  <div className="text-zinc-300 font-semibold">{totalHours.toFixed(1)} ч</div>
                                </div>
                                <button
                                  className="text-left hover:bg-zinc-600 rounded p-1 -m-1"
                                  onClick={() => {
                                    const allEntries = assignments.flatMap(a => a.rake_entries || []);
                                    setRakeLogInfo({ dealerName: name, entries: allEntries });
                                  }}
                                >
                                  <span className="text-zinc-500">Рейк:</span>
                                  <div className="text-amber-400 font-semibold underline">{formatMoney(totalRake)}</div>
                                </button>
                                <div>
                                  <span className="text-zinc-500">Зарплата:</span>
                                  <div className="text-green-400 font-semibold">{formatMoney(salary)}</div>
                                </div>
                              </div>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  </div>
                )}

                {/* Dealer history toggle */}
                {session.dealer_assignments && session.dealer_assignments.length > 1 && (
                  <button
                    className="text-xs text-blue-400 underline mb-2"
                    onClick={() => setShowDealerHistory(!showDealerHistory)}
                  >
                    {showDealerHistory
                      ? "Скрыть историю дилеров"
                      : `История дилеров (${session.dealer_assignments.length})`}
                  </button>
                )}

                {/* Dealer history list */}
                {showDealerHistory && session.dealer_assignments && session.dealer_assignments.length > 0 && (
                  <div className="mb-3 border-t border-zinc-600 pt-2">
                    <div className="text-xs text-zinc-500 mb-1">История дилеров:</div>
                    <div className="space-y-1">
                      {session.dealer_assignments.map((assignment) => (
                        <div key={assignment.id} className="text-xs text-zinc-300 flex justify-between">
                          <span>{assignment.dealer_username}</span>
                          <span className="text-zinc-500">
                            {formatTime(assignment.started_at)}
                            {assignment.ended_at ? ` - ${formatTime(assignment.ended_at)}` : " (текущий)"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Dealer management buttons for table_admin and superadmin */}
                {(user?.role === "superadmin" || user?.role === "table_admin") && (
                  <div className="grid grid-cols-2 gap-2 mt-4">
                    <button
                      className="rounded-xl bg-green-600 text-white py-2 text-sm active:bg-green-700 disabled:opacity-50"
                      onClick={() => setShowAddDealerModal(true)}
                      disabled={busy}
                    >
                      Добавить дилера
                    </button>
                    <button
                      className="rounded-xl bg-blue-600 text-white py-2 text-sm active:bg-blue-700 disabled:opacity-50"
                      onClick={() => setShowReplaceDealerModal(true)}
                      disabled={busy || (session.dealer_assignments && session.dealer_assignments.filter((a) => !a.ended_at).length > 1)}
                      title={
                        session.dealer_assignments && session.dealer_assignments.filter((a) => !a.ended_at).length > 1
                          ? "Невозможно заменить дилера при наличии нескольких активных дилеров"
                          : ""
                      }
                    >
                      Заменить дилера
                    </button>
                  </div>
                )}
              </div>
            )}

            {activeTab === "table" && (
              <>
                <SeatGrid seats={seats} onSeatClick={(seat) => setActiveSeatNo(seat.seat_no)} />

                {/* Separator */}
                <div className="border-t border-zinc-700 my-4" />

                <div className="flex gap-2">
                  <button
                    className="flex-1 rounded-xl px-3 py-2 bg-white text-zinc-900 active:bg-zinc-200 text-sm disabled:opacity-50"
                    onClick={() => tableId && loadOpenSession(tableId)}
                    disabled={loading || busy}
                  >
                    Обновить
                  </button>

                  <button
                    className="flex-1 rounded-xl px-3 py-2 bg-zinc-800 text-zinc-300 active:bg-zinc-700 text-sm disabled:opacity-50 border border-zinc-700"
                    onClick={showCloseConfirmation}
                    disabled={busy}
                  >
                    Закрыть сессию
                  </button>
                </div>
              </>
            )}

            <SeatActionSheet
              open={activeSeatNo !== null}
              seat={activeSeat}
              sessionId={session?.id ?? null}
              onClose={() => setActiveSeatNo(null)}
              onAssign={assignPlayer}
              onAdd={addChips}
              onClear={clearSeat}
            />

            <CashConfirmationModal
              open={showCashModal}
              amount={pendingChipAmount ?? 0}
              playerName={activeSeat?.player_name ?? null}
              seatNo={activeSeatNo ?? 0}
              onCash={() => pendingChipAmount && confirmChipPurchase(pendingChipAmount, "cash")}
              onCredit={() => pendingChipAmount && confirmChipPurchase(pendingChipAmount, "credit")}
              onCancel={() => {
                setShowCashModal(false);
                setPendingChipAmount(null);
              }}
              loading={busy}
            />

            <SessionCloseConfirmationModal
              open={showCloseModal}
              creditAmount={creditAmount}
              creditByPlayer={creditByPlayer}
              onConfirm={confirmCloseSession}
              onCancel={() => setShowCloseModal(false)}
              loading={busy}
            />

            <ReplaceDealerModal
              open={showReplaceDealerModal}
              sessionId={session.id}
              currentDealerId={session.dealer_id}
              onClose={() => setShowReplaceDealerModal(false)}
              onDealerReplaced={() => tableId && loadOpenSession(tableId)}
            />

            <AddDealerModal
              open={showAddDealerModal}
              sessionId={session.id}
              onClose={() => setShowAddDealerModal(false)}
              onDealerAdded={() => tableId && loadOpenSession(tableId)}
            />

            {removeDealerInfo && (
              <RemoveDealerModal
                open={true}
                sessionId={session.id}
                assignmentId={removeDealerInfo.assignmentId}
                dealerName={removeDealerInfo.dealerName}
                onClose={() => setRemoveDealerInfo(null)}
                onDealerRemoved={() => tableId && loadOpenSession(tableId)}
              />
            )}

            {rakeModalInfo && (
              <DealerRakeModal
                open={true}
                sessionId={session.id}
                assignmentId={rakeModalInfo.assignmentId}
                dealerName={rakeModalInfo.dealerName}
                currentRake={rakeModalInfo.currentRake}
                onClose={() => setRakeModalInfo(null)}
                onRakeUpdated={() => {
                  if (session?.table_id) {
                    loadOpenSession(session.table_id);
                  }
                }}
              />
            )}

            {/* Rake Log Fullscreen Overlay */}
            {rakeLogInfo && (
              <div className="fixed inset-0 z-50 bg-zinc-900 flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-zinc-700">
                  <div className="text-lg font-bold text-white">
                    Рейк: {rakeLogInfo.dealerName}
                  </div>
                  <button
                    className="text-zinc-400 hover:text-white text-2xl px-2"
                    onClick={() => setRakeLogInfo(null)}
                  >
                    ✕
                  </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-4">
                  {rakeLogInfo.entries.length === 0 ? (
                    <div className="text-zinc-500 text-center py-8">
                      Нет записей рейка
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {rakeLogInfo.entries
                        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                        .map((entry) => (
                          <div
                            key={entry.id}
                            className="rounded-lg bg-zinc-800 p-3 border border-zinc-700"
                          >
                            <div className="flex items-center justify-between">
                              <div className="text-amber-400 font-bold text-lg">
                                +{formatMoney(entry.amount)}
                              </div>
                              <div className="text-xs text-zinc-500">
                                {formatTime(entry.created_at)}
                              </div>
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

                {/* Footer */}
                <div className="p-4 border-t border-zinc-700 bg-zinc-800">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-zinc-400">Всего:</span>
                    <span className="text-amber-400 font-bold text-xl">
                      {formatMoney(rakeLogInfo.entries.reduce((sum, e) => sum + e.amount, 0))}
                    </span>
                  </div>
                  <button
                    className="w-full rounded-xl bg-zinc-700 text-white px-4 py-3 font-semibold hover:bg-zinc-600"
                    onClick={() => setRakeLogInfo(null)}
                  >
                    Закрыть
                  </button>
                </div>
              </div>
            )}

            {busy && (
              <div className="fixed bottom-4 left-0 right-0 flex justify-center pointer-events-none">
                <div className="rounded-xl bg-black/80 text-white px-4 py-2 text-sm">
                  Сохранение…
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </RequireAuth>
  );
}
