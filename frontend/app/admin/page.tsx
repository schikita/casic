"use client";

import { Suspense, useEffect, useMemo, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import TopMenu from "@/components/TopMenu";
import { apiJson } from "@/lib/api";
import { isNonEmpty, toInt, formatDateTime as fmtDateTime } from "@/lib/utils";
import { DEFAULT_SEATS_COUNT, DEFAULT_PURCHASE_LIMIT, MIN_PURCHASE_LIMIT, MAX_PURCHASE_LIMIT, MIN_SEATS_COUNT, MAX_SEATS_COUNT, MIN_PASSWORD_LENGTH, SUCCESS_MESSAGE_DURATION } from "@/lib/constants";
import type { UserRole, Table, User, ChipPurchase } from "@/lib/types";

function roleLabel(role: UserRole): string {
  if (role === "superadmin") return "Суперадмин";
  if (role === "table_admin") return "Админ стола";
  if (role === "waiter") return "Официант";
  return "Дилер";
}

const inputDark =
  "rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-white/15 placeholder-zinc-500";

const selectDark =
  "rounded-xl border border-zinc-700 bg-zinc-800 text-white px-3 py-3 text-base focus:outline-none focus:ring-2 focus:ring-white/15";

function AdminPageContent() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  
  const [tab, setTab] = useState<"tables" | "users" | "purchases">("tables");
  
  // Determine available roles based on current user's role
  const availableRoles = useMemo(() => {
    if (!user) return [];
    if (user.role === "superadmin") return ["table_admin"];
    if (user.role === "table_admin") return ["dealer", "waiter"];
    return [];
  }, [user]);
  
  // Check if current user can manage tables (superadmin only)
  const canManageTables = user?.role === "superadmin";

  // Read tab from URL query parameter
  useEffect(() => {
    const tabFromUrl = searchParams.get("tab") as "tables" | "users" | "purchases" | null;
    if (tabFromUrl) {
      setTab(tabFromUrl);
    }
  }, [searchParams]);

  const [tables, setTables] = useState<Table[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [purchases, setPurchases] = useState<ChipPurchase[]>([]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  // ------- Tables create form -------
  const [tableName, setTableName] = useState("");
  const [tableSeats, setTableSeats] = useState<number>(DEFAULT_SEATS_COUNT);

  // ------- Users create form -------
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<UserRole>("dealer");
  const [newTableId, setNewTableId] = useState<number | null>(null);
  const [newHourlyRate, setNewHourlyRate] = useState<string>("");
  
  // Initialize newRole based on available roles
  useEffect(() => {
    if (availableRoles.length > 0 && !availableRoles.includes(newRole)) {
      setNewRole(availableRoles[0] as UserRole);
    }
  }, [availableRoles, newRole]);

  // ------- Delete confirmation dialog -------
  const [deleteConfirmUserId, setDeleteConfirmUserId] = useState<number | null>(null);

  // ------- Purchases controls -------
  const [purchaseLimit, setPurchaseLimit] = useState<number>(DEFAULT_PURCHASE_LIMIT);

  // ------- Per-user edit drafts -------
  const [draftRole, setDraftRole] = useState<Record<number, UserRole>>({});
  const [draftTableId, setDraftTableId] = useState<Record<number, number | null>>({});
  const [draftPassword, setDraftPassword] = useState<Record<number, string>>(
    {}
  );
  const [draftHourlyRate, setDraftHourlyRate] = useState<Record<number, string>>({});

  const tablesById = useMemo(() => {
    const m = new Map<number, Table>();
    for (const t of tables) m.set(t.id, t);
    return m;
  }, [tables]);

  const clearNotices = useCallback(() => {
    setError(null);
    setOk(null);
  }, []);

  const showOk = useCallback((msg: string) => {
    setOk(msg);
    setTimeout(() => setOk(null), SUCCESS_MESSAGE_DURATION);
  }, []);

  const normalizeUserDrafts = useCallback((list: User[]) => {
    const r: Record<number, UserRole> = {};
    const t: Record<number, number | null> = {};
    const p: Record<number, string> = {};
    const h: Record<number, string> = {};
    for (const u of list) {
      r[u.id] = u.role;
      t[u.id] = u.table_id;
      p[u.id] = "";
      h[u.id] = u.hourly_rate !== null ? String(u.hourly_rate) : "";
    }
    setDraftRole(r);
    setDraftTableId(t);
    setDraftPassword(p);
    setDraftHourlyRate(h);
  }, []);

  const loadTablesOnly = useCallback(async () => {
    clearNotices();
    setBusy(true);
    try {
      const t = await apiJson<Table[]>("/api/admin/tables");
      setTables(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки столов");
    } finally {
      setBusy(false);
    }
  }, [clearNotices]);

  const loadUsersOnly = useCallback(async () => {
    clearNotices();
    setBusy(true);
    try {
      const u = await apiJson<User[]>("/api/admin/users");
      setUsers(u);
      normalizeUserDrafts(u);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки пользователей");
    } finally {
      setBusy(false);
    }
  }, [clearNotices, normalizeUserDrafts]);

  const loadPurchasesOnly = useCallback(async () => {
    clearNotices();
    setBusy(true);
    try {
      const limit = Math.min(Math.max(toInt(purchaseLimit, DEFAULT_PURCHASE_LIMIT), MIN_PURCHASE_LIMIT), MAX_PURCHASE_LIMIT);
      const list = await apiJson<ChipPurchase[]>(
        "/api/admin/chip-purchases?limit=" + limit
      );
      setPurchases(list);
      showOk("Покупки обновлены");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки покупок");
    } finally {
      setBusy(false);
    }
  }, [clearNotices, showOk, purchaseLimit]);

  const loadAll = useCallback(async () => {
    clearNotices();
    setBusy(true);
    try {
      const [t, u] = await Promise.all([
        apiJson<Table[]>("/api/admin/tables"),
        apiJson<User[]>("/api/admin/users"),
      ]);
      setTables(t);
      setUsers(u);
      normalizeUserDrafts(u);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки админки");
    } finally {
      setBusy(false);
    }
  }, [clearNotices, normalizeUserDrafts]);

  useEffect(() => {
    if (!user) return;
    // Load data based on user role
    if (user.role === "superadmin") {
      loadAll().catch(() => {});
    } else if (user.role === "table_admin") {
      // Table admin only needs to load users and tables for dropdown
      loadUsersOnly().catch(() => {});
      if (tables.length === 0) loadTablesOnly().catch(() => {});
    }
  }, [user, loadAll, loadUsersOnly, loadTablesOnly, tables.length]);

  useEffect(() => {
    if (!user) return;
    if (user.role !== "superadmin") return;

    // Чтобы в селектах были варианты столов даже на вкладке пользователей
    if (tables.length === 0) loadTablesOnly().catch(() => {});

    if (tab === "purchases" && purchases.length === 0) {
      loadPurchasesOnly().catch(() => {});
    }
  }, [user, tab, tables.length, purchases.length, loadTablesOnly, loadPurchasesOnly]);

  const createTable = useCallback(async () => {
    clearNotices();

    const name = tableName.trim();
    const seats = toInt(tableSeats, DEFAULT_SEATS_COUNT);

    if (!isNonEmpty(name)) {
      setError("Введите название стола");
      return;
    }
    if (!(seats >= MIN_SEATS_COUNT && seats <= MAX_SEATS_COUNT)) {
      setError("Количество мест должно быть от 1 до 60");
      return;
    }

    setBusy(true);
    try {
      await apiJson<Table>("/api/admin/tables", {
        method: "POST",
        body: JSON.stringify({ name, seats_count: seats }),
      });

      setTableName("");
      setTableSeats(DEFAULT_SEATS_COUNT);
      await loadTablesOnly();
      showOk("Стол создан");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка создания стола");
    } finally {
      setBusy(false);
    }
  }, [clearNotices, showOk, tableName, tableSeats, loadTablesOnly]);

  const createUser = useCallback(async () => {
    clearNotices();

    const username = newUsername.trim();
    const password = newPassword;
    const role = newRole;

    if (!isNonEmpty(username)) {
      setError("Введите логин");
      return;
    }
    
    // Password is required for table_admin, optional for dealer/waiter
    if (role === "table_admin") {
      if (!isNonEmpty(password) || password.length < MIN_PASSWORD_LENGTH) {
        setError("Пароль обязателен для админа стола (минимум 4 символа)");
        return;
      }
    } else {
      // For dealer/waiter, password is optional but if provided must be valid
      if (isNonEmpty(password) && password.length < MIN_PASSWORD_LENGTH) {
        setError("Пароль должен быть минимум 4 символа");
        return;
      }
    }
    
    // hourly_rate is required for dealer/waiter
    if ((role === "dealer" || role === "waiter") && !isNonEmpty(newHourlyRate)) {
      setError("Ставка в час обязательна для дилера и официанта");
      return;
    }

    const table_id = role === "table_admin" ? newTableId : null;
    const hourly_rate = (role === "dealer" || role === "waiter") && newHourlyRate !== ""
      ? Number(newHourlyRate)
      : null;

    setBusy(true);
    try {
      await apiJson<User>("/api/admin/users", {
        method: "POST",
        body: JSON.stringify({
          username,
          password: isNonEmpty(password) ? password : null,
          role,
          table_id,
          is_active: true,
          hourly_rate,
        }),
      });

      setNewUsername("");
      setNewPassword("");
      setNewRole(availableRoles[0] as UserRole);
      setNewTableId(null);
      setNewHourlyRate("");

      await loadUsersOnly();
      showOk("Пользователь создан");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка создания пользователя");
    } finally {
      setBusy(false);
    }
  }, [clearNotices, showOk, newUsername, newPassword, newRole, newTableId, newHourlyRate, loadUsersOnly, availableRoles]);

  const saveUser = useCallback(async (userId: number) => {
    clearNotices();

    const role = draftRole[userId];
    const table_id = role === "table_admin" ? draftTableId[userId] : null;
    const password = String(draftPassword[userId] ?? "");
    const hourlyRateStr = draftHourlyRate[userId] ?? "";

    const body: Record<string, unknown> = {
      role,
    };

    if (role === "table_admin" && table_id !== undefined) {
      body.table_id = table_id;
    }

    if (role === "dealer" || role === "waiter") {
      body.hourly_rate = hourlyRateStr !== "" ? Number(hourlyRateStr) : null;
    }

    if (isNonEmpty(password)) {
      if (password.length < MIN_PASSWORD_LENGTH) {
        setError("Новый пароль должен быть минимум 4 символа");
        return;
      }
      body.password = password;
    }

    setBusy(true);
    try {
      await apiJson<User>("/api/admin/users/" + userId, {
        method: "PUT",
        body: JSON.stringify(body),
      });

      setDraftPassword((prev) => ({ ...prev, [userId]: "" }));
      await loadUsersOnly();
      showOk("Изменения сохранены");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка сохранения пользователя");
    } finally {
      setBusy(false);
    }
  }, [clearNotices, showOk, draftRole, draftTableId, draftPassword, draftHourlyRate, loadUsersOnly]);

  const setRoleForUser = useCallback((userId: number, role: UserRole) => {
    setDraftRole((prev) => ({ ...prev, [userId]: role }));
  }, []);

  const deleteUser = useCallback(async (userId: number) => {
    clearNotices();
    setBusy(true);
    try {
      await apiJson<User>("/api/admin/users/" + userId, {
        method: "PUT",
        body: JSON.stringify({ is_active: false }),
      });
      setDeleteConfirmUserId(null);
      await loadUsersOnly();
      showOk("Пользователь удалён");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка удаления пользователя");
    } finally {
      setBusy(false);
    }
  }, [clearNotices, showOk, loadUsersOnly]);

  const refreshCurrentTab = useCallback(() => {
    if (tab === "tables") return loadTablesOnly();
    if (tab === "users") return loadUsersOnly();
    return loadPurchasesOnly();
  }, [tab, loadTablesOnly, loadUsersOnly, loadPurchasesOnly]);

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
            Доступ запрещён
          </div>
        </main>
      </RequireAuth>
    );
  }

  return (
    <RequireAuth>
      <main className="p-3 max-w-md mx-auto">
        <TopMenu />

        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-xl font-bold text-white">Админка</div>
            <div className="text-xs text-zinc-400">
              {user.role === "superadmin" ? "Управление системой" : "Управление персоналом"}
            </div>
          </div>

          <button
            className="rounded-xl bg-black text-white px-3 py-2 text-sm disabled:opacity-60 hover:bg-zinc-800/90"
            onClick={() => refreshCurrentTab().catch(() => {})}
            disabled={busy}
          >
            Обновить
          </button>
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-900/50 text-red-200 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {ok && (
          <div className="mb-3 rounded-xl bg-green-50 text-green-800 px-3 py-2 text-sm">
            {ok}
          </div>
        )}

        {tab === "tables" && canManageTables && (
          <>
            <div className="rounded-xl bg-zinc-900 p-4 mb-3">
              <div className="text-white font-semibold mb-2">Создать стол</div>

              <div className="grid gap-2">
                <input
                  value={tableName}
                  onChange={(e) => setTableName(e.target.value)}
                  className={inputDark}
                  placeholder="Название (например: Стол 1)"
                />

                <input
                  type="number"
                  value={tableSeats}
                  onChange={(e) => setTableSeats(Number(e.target.value))}
                  className={inputDark}
                  placeholder="Мест"
                  min={MIN_SEATS_COUNT}
                  max={MAX_SEATS_COUNT}
                />

                <button
                  className="rounded-xl bg-green-600 text-white px-4 py-3 font-semibold disabled:opacity-60 hover:bg-green-700/90"
                  onClick={createTable}
                  disabled={busy || !isNonEmpty(tableName)}
                >
                  Создать
                </button>

                <div className="text-xs text-zinc-400">
                  Рекомендуется держать seats_count в диапазоне 1–60.
                </div>
              </div>
            </div>

            <div className="rounded-xl bg-zinc-900 p-4">
              <div className="text-white font-semibold mb-2">
                Существующие столы ({tables.length})
              </div>

              {tables.length === 0 ? (
                <div className="rounded-xl bg-black text-white/70 px-3 py-3 text-sm">
                  Столов пока нет. Создайте первый стол выше.
                </div>
              ) : (
                <div className="grid gap-2">
                  {tables.map((t) => (
                    <div
                      key={t.id}
                      className="rounded-xl bg-black text-white px-4 py-3"
                    >
                      <div className="flex items-center justify-between">
                        <div className="font-semibold">{t.name}</div>
                        <div className="text-xs text-white/60">ID: {t.id}</div>
                      </div>
                      <div className="text-sm text-zinc-300">
                        Мест:{" "}
                        <span className="text-white">{t.seats_count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {tab === "users" && (
          <>
            <div className="rounded-xl bg-zinc-900 p-4 mb-3">
              <div className="text-white font-semibold mb-2">
                Создать пользователя
              </div>

              <div className="grid gap-2">
                <input
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className={inputDark}
                  placeholder="Логин"
                />

                <input
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className={inputDark}
                  placeholder={newRole === "table_admin" ? "Пароль *" : "Пароль (если нужно)"}
                  type="password"
                />

                <select
                  className={selectDark}
                  value={newRole}
                  onChange={(e) => {
                    setNewRole(e.target.value as UserRole);
                  }}
                >
                  {availableRoles.map((role) => (
                      <option key={role} value={role}>
                        {roleLabel(role as UserRole)}
                      </option>
                    ))}
                </select>

                {newRole === "table_admin" && (
                  <select
                    className={selectDark}
                    value={newTableId ?? ""}
                    onChange={(e) => {
                      setNewTableId(
                        e.target.value === "" ? null : Number(e.target.value)
                      );
                    }}
                  >
                    <option value="">Выберите стол</option>
                    {tables.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                )}

                {(newRole === "dealer" || newRole === "waiter") && (
                  <input
                    type="number"
                    value={newHourlyRate}
                    onChange={(e) => setNewHourlyRate(e.target.value)}
                    className={inputDark}
                    placeholder="Ставка в час *"
                    min={0}
                  />
                )}

                <button
                  className="rounded-xl bg-green-600 text-white px-4 py-3 font-semibold disabled:opacity-60 hover:bg-green-700/90"
                  onClick={createUser}
                  disabled={
                    busy ||
                    !isNonEmpty(newUsername) ||
                    (newRole === "table_admin" && !isNonEmpty(newPassword)) ||
                    ((newRole === "dealer" || newRole === "waiter") && !isNonEmpty(newHourlyRate))
                  }
                >
                  Создать
                </button>
              </div>
            </div>

            <div className="rounded-xl bg-zinc-900 p-4">
              <div className="text-white font-semibold mb-2">
                Пользователи ({users.length})
              </div>

              {users.length === 0 ? (
                <div className="rounded-xl bg-black text-white/70 px-3 py-3 text-sm">
                  Пользователей пока нет.
                </div>
              ) : (
                <div className="grid gap-2">
                  {(() => {
                    const activeUsers = users.filter((u) => u.is_active);
                    const inactiveUsers = users.filter((u) => !u.is_active);
                    const sortedUsers = [...activeUsers, ...inactiveUsers];

                    return sortedUsers.map((u, idx) => {
                      const role = draftRole[u.id] ?? u.role;
                      const tableId = draftTableId[u.id] ?? u.table_id;
                      const pwd = draftPassword[u.id] ?? "";
                      const hourlyRate = draftHourlyRate[u.id] ?? (u.hourly_rate !== null ? String(u.hourly_rate) : "");
                      const table = tableId !== null ? tablesById.get(tableId) : null;
                      const showSeparator = idx === activeUsers.length && inactiveUsers.length > 0;

                      return (
                        <div key={u.id}>
                          {showSeparator && (
                            <div className="flex items-center gap-3 my-3">
                              <div className="flex-1 h-px bg-zinc-700" />
                              <span className="text-xs text-zinc-500">Удалённые</span>
                              <div className="flex-1 h-px bg-zinc-700" />
                            </div>
                          )}
                          <div
                            className={
                              "rounded-xl text-white px-4 py-3 " +
                              (u.is_active ? "bg-black" : "bg-black/50 opacity-70")
                            }
                          >
                            <div className="font-semibold">
                              {u.username}{" "}
                              <span className="text-xs text-white/60">
                                ID {u.id}
                              </span>
                            </div>
                            <div className="text-xs text-zinc-400">
                              Текущая роль: {roleLabel(u.role)}
                              {u.table_id !== null && table && (
                                <span className="ml-2">
                                  • Стол: {table.name}
                                </span>
                              )}
                            </div>

                            <div className="grid gap-2 mt-3">
                              <select
                                className={selectDark}
                                value={role}
                                onChange={(e) =>
                                  setRoleForUser(u.id, e.target.value as UserRole)
                                }
                                disabled={busy}
                              >
                                {availableRoles.map((r) => (
                                  <option key={r} value={r}>
                                    {roleLabel(r as UserRole)}
                                  </option>
                                ))}
                              </select>

                              {role === "table_admin" && (
                                <select
                                  className={selectDark}
                                  value={tableId ?? ""}
                                  onChange={(e) => {
                                    setDraftTableId((prev) => ({
                                      ...prev,
                                      [u.id]:
                                        e.target.value === ""
                                          ? null
                                          : Number(e.target.value),
                                    }));
                                  }}
                                  disabled={busy}
                                >
                                  <option value="">Выберите стол</option>
                                  {tables.map((t) => (
                                    <option key={t.id} value={t.id}>
                                      {t.name}
                                    </option>
                                  ))}
                                </select>
                              )}

                              {(role === "dealer" || role === "waiter") && (
                                <input
                                  type="number"
                                  value={hourlyRate}
                                  onChange={(e) =>
                                    setDraftHourlyRate((prev) => ({
                                      ...prev,
                                      [u.id]: e.target.value,
                                    }))
                                  }
                                  className={inputDark}
                                  placeholder="Ставка в час"
                                  min={0}
                                  disabled={busy}
                                />
                              )}

                              <input
                                value={pwd}
                                onChange={(e) =>
                                  setDraftPassword((prev) => ({
                                    ...prev,
                                    [u.id]: e.target.value,
                                  }))
                                }
                                className={inputDark}
                                placeholder={role === "table_admin" ? "Новый пароль *" : "Новый пароль (если нужно)"}
                                type="password"
                                disabled={busy}
                              />

                              <div className="flex gap-2">
                                <button
                                  className="flex-1 rounded-xl bg-zinc-900 text-white px-4 py-3 font-semibold disabled:opacity-60 hover:bg-black/90"
                                  onClick={() => saveUser(u.id)}
                                  disabled={busy}
                                >
                                  Сохранить изменения
                                </button>

                                {u.is_active && u.role !== "superadmin" && (
                                  <button
                                    className="rounded-xl bg-red-600 text-white px-4 py-3 font-semibold disabled:opacity-60 hover:bg-red-700/90"
                                    onClick={() => setDeleteConfirmUserId(u.id)}
                                    disabled={busy}
                                    title="Удалить пользователя"
                                  >
                                    Удалить
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    });
                  })()}
                </div>
              )}
            </div>

            {/* Delete confirmation dialog */}
            {deleteConfirmUserId !== null && (
              <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
                <div className="rounded-xl bg-zinc-900 p-6 max-w-sm w-full mx-4">
                  <div className="text-white font-semibold text-lg mb-2">
                    Подтверждение
                  </div>
                  <div className="text-white/80 mb-4">
                    Вы уверены, что хотите удалить пользователя{" "}
                    <span className="font-semibold">
                      {users.find((u) => u.id === deleteConfirmUserId)?.username}
                    </span>
                    ?
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="flex-1 rounded-xl bg-zinc-800 text-white px-4 py-3 font-semibold disabled:opacity-60 hover:bg-zinc-700/90"
                      onClick={() => setDeleteConfirmUserId(null)}
                      disabled={busy}
                    >
                      Отмена
                    </button>
                    <button
                      className="flex-1 rounded-xl bg-red-600 text-white px-4 py-3 font-semibold disabled:opacity-60 hover:bg-red-700/90"
                      onClick={() => deleteUser(deleteConfirmUserId)}
                      disabled={busy}
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {tab === "purchases" && (
          <>
            <div className="rounded-xl bg-zinc-900 p-4 mb-3">
              <div className="text-white font-semibold mb-2">
                Последние покупки фишек
              </div>

              <div className="grid gap-2">
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    value={purchaseLimit}
                    onChange={(e) => setPurchaseLimit(Number(e.target.value))}
                    className={inputDark}
                    min={MIN_PURCHASE_LIMIT}
                    max={MAX_PURCHASE_LIMIT}
                    placeholder="Лимит (например 100)"
                  />
                  <button
                    className="rounded-xl bg-green-600 text-white px-4 py-3 font-semibold disabled:opacity-60 hover:bg-green-700/90"
                    onClick={() => loadPurchasesOnly().catch(() => {})}
                    disabled={busy}
                  >
                    Загрузить
                  </button>
                </div>

                <div className="text-xs text-zinc-400">
                  Показывает последние операции “добавить фишки”: дата/время,
                  стол, место, сумма, кто выдал.
                </div>
              </div>
            </div>

            <div className="rounded-xl bg-zinc-900 p-4">
              <div className="text-white font-semibold mb-2">
                Операции ({purchases.length})
              </div>

              {purchases.length === 0 ? (
                <div className="rounded-xl bg-black text-white/70 px-3 py-3 text-sm">
                  Пока нет покупок (или не настроен эндпоинт
                  /api/admin/chip-purchases).
                </div>
              ) : (
                <div className="grid gap-2">
                  {purchases.map((p) => (
                    <div
                      key={p.id}
                      className="rounded-xl bg-black text-white px-4 py-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-semibold">
                          {p.table_name}{" "}
                          <span className="text-xs text-white/60">
                            (ID {p.table_id})
                          </span>
                        </div>
                        <div className="text-xs text-white/60">#{p.id}</div>
                      </div>

                      <div className="mt-1 text-sm text-zinc-300">
                        Место: <span className="text-white">{p.seat_no}</span> •
                        Сумма:{" "}
                        <span className="text-white font-semibold">
                          {p.amount}
                        </span>
                      </div>

                      <div className="mt-1 text-xs text-zinc-400">
                        {fmtDateTime(p.created_at)}
                        {" • "}
                        Выдал:{" "}
                        {p.created_by_username
                          ? p.created_by_username
                          : p.created_by_user_id != null
                          ? `user_id ${p.created_by_user_id}`
                          : "—"}
                        {p.session_id ? ` • session ${p.session_id}` : ""}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {busy && (
          <div className="fixed bottom-4 left-0 right-0 flex justify-center pointer-events-none">
            <div className="rounded-xl bg-black/80 text-white px-4 py-2 text-sm">
              Выполнение…
            </div>
          </div>
        )}
      </main>
    </RequireAuth>
  );
}

export default function AdminPage() {
  return (
    <Suspense fallback={<div className="p-4 text-white">Загрузка…</div>}>
      <AdminPageContent />
    </Suspense>
  );
}

