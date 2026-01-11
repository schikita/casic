"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import SeatGrid from "@/components/SeatGrid";
import SeatActionSheet from "@/components/SeatActionSheet";
import StartSessionModal from "@/components/StartSessionModal";
import CashConfirmationModal from "@/components/CashConfirmationModal";
import SessionCloseConfirmationModal from "@/components/SessionCloseConfirmationModal";
import ReplaceDealerModal from "@/components/ReplaceDealerModal";
import TopMenu from "@/components/TopMenu";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import { apiJson, getSelectedTableId, setSelectedTableId } from "@/lib/api";
import { normalizeTableId, getErrorMessage, formatTime } from "@/lib/utils";
import type { Seat, Session, Table } from "@/lib/types";

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
  const [showDealerHistory, setShowDealerHistory] = useState<boolean>(false);
  const [rake, setRake] = useState<{ total_rake: number; total_buyins: number; total_cashouts: number; total_credit: number } | null>(null);

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
      if (user.role !== "superadmin") {
        const tid = normalizeTableId(user.table_id);
        setTableId(tid);

        if (!tid) {
          setSession(null);
          setSeats([]);
          setLoading(false);
        }

        return;
      }

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

  const assignPlayer = useCallback(async (playerName: string | null) => {
    if (!session || !activeSeatNo) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await apiJson<Seat>(
        "/api/sessions/" + session.id + "/seats/" + activeSeatNo,
        {
          method: "PUT",
          body: JSON.stringify({ player_name: playerName }),
        }
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

  useEffect(() => {
    if (!user) return;
    loadTablesAndSelect();
  }, [user, loadTablesAndSelect]);

  useEffect(() => {
    if (!tableId) return;
    loadOpenSession(tableId);
  }, [tableId, loadOpenSession]);

  const totals = useMemo(() => {
    const chips = seats.reduce((acc, s) => acc + (s.total || 0), 0);
    return { chips };
  }, [seats]);

  return (
    <RequireAuth>
      <main className="p-3 max-w-md mx-auto">
        <TopMenu />

        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="text-xl font-bold text-black">Стол</div>
            <div className="text-xs text-zinc-500">
              {activeTable ? activeTable.name : ""}
              {session
                ? " • сессия " + session.date + " (" + session.status + ")"
                : " • сессия не открыта"}
            </div>
          </div>

          {user?.role === "superadmin" && (
            <select
              className="rounded-xl border border-zinc-300 bg-white text-black px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-zinc-400"
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
          <div className="rounded-xl bg-zinc-100 px-3 py-3 text-sm text-zinc-600">
            Загрузка…
          </div>
        )}

        {!loading && !tableId && (
          <div className="rounded-xl bg-zinc-100 text-zinc-700 px-3 py-3 text-sm rounded-xl">
            Нет доступного стола. Назначьте table_id админу стола или создайте
            стол в админке.
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
              <div className="rounded-xl bg-zinc-100 px-3 py-3 text-sm text-zinc-700">
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
            <div className="mb-3 grid grid-cols-3 gap-2">
              <div className="rounded-xl bg-zinc-900 text-white px-3 py-3">
                <div className="text-xs text-zinc-300">
                  Фишек на столе
                </div>
                <div className="text-xl font-bold tabular-nums">
                  {totals.chips}
                </div>
              </div>
              <div className="rounded-xl bg-zinc-900 text-white px-3 py-3">
                <div className="text-xs text-zinc-300">
                  Рейк (грязный)
                </div>
                <div className="text-xl font-bold tabular-nums">
                  {rake?.total_rake ?? 0}
                </div>
              </div>
              <div className="rounded-xl bg-red-900 text-white px-3 py-3">
                <div className="text-xs text-red-200">
                  Кредит
                </div>
                <div className="text-xl font-bold tabular-nums">
                  -{rake?.total_credit ?? 0}
                </div>
              </div>
            </div>

            <div className="mb-3 rounded-xl bg-zinc-100 p-4 border border-zinc-200">
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <div className="text-xs font-medium text-zinc-600 mb-1">
                    Дилер
                  </div>
                  <div className="text-sm font-semibold text-zinc-900">
                    {session.dealer?.username || "—"}
                  </div>
                </div>
                {session.waiter && (
                  <div>
                    <div className="text-xs font-medium text-zinc-600 mb-1">
                      Официант
                    </div>
                    <div className="text-sm font-semibold text-zinc-900">
                      {session.waiter.username}
                    </div>
                  </div>
                )}
              </div>

              {/* Dealer history toggle */}
              {session.dealer_assignments && session.dealer_assignments.length > 1 && (
                <button
                  className="text-xs text-blue-600 underline mb-2"
                  onClick={() => setShowDealerHistory(!showDealerHistory)}
                >
                  {showDealerHistory ? "Скрыть историю дилеров" : `История дилеров (${session.dealer_assignments.length})`}
                </button>
              )}

              {/* Dealer history list */}
              {showDealerHistory && session.dealer_assignments && session.dealer_assignments.length > 0 && (
                <div className="mb-3 border-t border-zinc-200 pt-2">
                  <div className="text-xs text-zinc-500 mb-1">История дилеров:</div>
                  <div className="space-y-1">
                    {session.dealer_assignments.map((assignment) => (
                      <div key={assignment.id} className="text-xs text-zinc-700 flex justify-between">
                        <span>{assignment.dealer_username}</span>
                        <span className="text-zinc-400">
                          {formatTime(assignment.started_at)}
                          {assignment.ended_at ? ` - ${formatTime(assignment.ended_at)}` : " (текущий)"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Replace dealer button for table_admin and superadmin */}
              {(user?.role === "superadmin" || user?.role === "table_admin") && (
                <button
                  className="w-full rounded-xl bg-blue-600 text-white py-2 text-sm active:bg-blue-700 disabled:opacity-50"
                  onClick={() => setShowReplaceDealerModal(true)}
                  disabled={busy}
                >
                  Заменить дилера
                </button>
              )}
            </div>

            <div className="flex gap-2 mb-3">
              <button
                className="flex-1 rounded-xl px-3 py-2 bg-black text-white active:bg-zinc-800 text-sm disabled:opacity-50 hover:bg-zinc-800/90"
                onClick={() => tableId && loadOpenSession(tableId)}
                disabled={loading || busy}
              >
                Обновить
              </button>

              <button
                className="flex-1 rounded-xl px-3 py-2 bg-zinc-100 text-black active:bg-zinc-200 text-sm disabled:opacity-50 hover:bg-zinc-200/90"
                onClick={showCloseConfirmation}
                disabled={busy}
              >
                Закрыть сессию
              </button>
            </div>

            <SeatGrid
              seats={seats}
              onSeatClick={(seat) => setActiveSeatNo(seat.seat_no)}
            />

            <SeatActionSheet
              open={activeSeatNo !== null}
              seat={activeSeat}
              onClose={() => setActiveSeatNo(null)}
              onAssign={assignPlayer}
              onAdd={addChips}
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
