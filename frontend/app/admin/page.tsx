"use client";

import { useEffect, useMemo, useState } from "react";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/components/auth/AuthContext";
import TopMenu from "@/components/TopMenu";
import { apiJson } from "@/lib/api";

type UserRole = "superadmin" | "table_admin" | "dealer";

type Table = {
  id: number;
  name: string;
  seats_count: number;
};

type User = {
  id: number;
  username: string;
  role: UserRole;
  table_id: number | null;
  is_active: boolean;
};

type ChipPurchase = {
  id: number;
  table_id: number;
  table_name: string;
  session_id: string | null;
  seat_no: number;
  amount: number;
  created_at: string; // ISO
  created_by_user_id: number | null;
  created_by_username: string | null;
};

function isNonEmpty(v: any) {
  return String(v ?? "").trim().length > 0;
}

function toInt(v: any, fallback: number) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function roleLabel(role: UserRole) {
  if (role === "superadmin") return "Суперадмин";
  if (role === "table_admin") return "Админ стола";
  return "Дилер";
}

function fmtDateTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

const inputDark =
  "rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-3 text-base text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-white/15";

const selectDark =
  "rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-3 text-base text-white focus:outline-none focus:ring-2 focus:ring-white/15";

export default function AdminPage() {
  const { user } = useAuth();

  const [tab, setTab] = useState<"tables" | "users" | "purchases">("tables");

  const [tables, setTables] = useState<Table[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [purchases, setPurchases] = useState<ChipPurchase[]>([]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  // ------- Tables create form -------
  const [tableName, setTableName] = useState("");
  const [tableSeats, setTableSeats] = useState<number>(24);

  // ------- Users create form -------
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<UserRole>("dealer");
  const [newTableId, setNewTableId] = useState("");
  const [newActive, setNewActive] = useState(true);

  // ------- Purchases controls -------
  const [purchaseLimit, setPurchaseLimit] = useState<number>(100);

  // ------- Per-user edit drafts -------
  const [draftRole, setDraftRole] = useState<Record<number, UserRole>>({});
  const [draftTableId, setDraftTableId] = useState<Record<number, string>>({});
  const [draftActive, setDraftActive] = useState<Record<number, boolean>>({});
  const [draftPassword, setDraftPassword] = useState<Record<number, string>>(
    {}
  );

  const tablesById = useMemo(() => {
    const m = new Map<number, Table>();
    for (const t of tables) m.set(t.id, t);
    return m;
  }, [tables]);

  function clearNotices() {
    setError(null);
    setOk(null);
  }

  function showOk(msg: string) {
    setOk(msg);
    setTimeout(() => setOk(null), 2500);
  }

  function normalizeUserDrafts(list: User[]) {
    const r: Record<number, UserRole> = {};
    const t: Record<number, string> = {};
    const a: Record<number, boolean> = {};
    const p: Record<number, string> = {};
    for (const u of list) {
      r[u.id] = u.role;
      t[u.id] = u.table_id == null ? "" : String(u.table_id);
      a[u.id] = !!u.is_active;
      p[u.id] = "";
    }
    setDraftRole(r);
    setDraftTableId(t);
    setDraftActive(a);
    setDraftPassword(p);
  }

  async function loadTablesOnly() {
    clearNotices();
    setBusy(true);
    try {
      const t = await apiJson<Table[]>("/api/admin/tables");
      setTables(t);
    } catch (e: any) {
      setError(e?.message ?? "Ошибка загрузки столов");
    } finally {
      setBusy(false);
    }
  }

  async function loadUsersOnly() {
    clearNotices();
    setBusy(true);
    try {
      const u = await apiJson<User[]>("/api/admin/users");
      setUsers(u);
      normalizeUserDrafts(u);
    } catch (e: any) {
      setError(e?.message ?? "Ошибка загрузки пользователей");
    } finally {
      setBusy(false);
    }
  }

  async function loadPurchasesOnly() {
    clearNotices();
    setBusy(true);
    try {
      const limit = Math.min(Math.max(toInt(purchaseLimit, 100), 1), 500);
      const list = await apiJson<ChipPurchase[]>(
        "/api/admin/chip-purchases?limit=" + limit
      );
      setPurchases(list);
      showOk("Покупки обновлены");
    } catch (e: any) {
      setError(e?.message ?? "Ошибка загрузки покупок");
    } finally {
      setBusy(false);
    }
  }

  async function loadAll() {
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
    } catch (e: any) {
      setError(e?.message ?? "Ошибка загрузки админки");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!user) return;
    if (user.role !== "superadmin") return;
    loadAll().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    if (!user) return;
    if (user.role !== "superadmin") return;

    // Чтобы в селектах были варианты столов даже на вкладке пользователей
    if (tables.length === 0) loadTablesOnly().catch(() => {});

    if (tab === "purchases" && purchases.length === 0) {
      loadPurchasesOnly().catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, user?.id]);

  async function createTable() {
    clearNotices();

    const name = tableName.trim();
    const seats = toInt(tableSeats, 24);

    if (!isNonEmpty(name)) {
      setError("Введите название стола");
      return;
    }
    if (!(seats >= 1 && seats <= 60)) {
      setError("Количество мест должно быть от 1 до 60");
      return;
    }

    setBusy(true);
    try {
      await apiJson<TableOut>("/api/admin/tables", {
        method: "POST",
        body: JSON.stringify({ name, seats_count: seats }),
      });

      setTableName("");
      setTableSeats(24);
      await loadTablesOnly();
      showOk("Стол создан");
    } catch (e: any) {
      setError(e?.message ?? "Ошибка создания стола");
    } finally {
      setBusy(false);
    }
  }

  async function createUser() {
    clearNotices();

    const username = newUsername.trim();
    const password = newPassword;

    if (!isNonEmpty(username)) {
      setError("Введите логин");
      return;
    }
    if (!isNonEmpty(password) || password.length < 4) {
      setError("Пароль должен быть минимум 4 символа");
      return;
    }

    const role = newRole;
    let table_id = newTableId ? toInt(newTableId, 0) : null;

    if (role !== "superadmin") {
      if (!table_id) {
        setError("Для этой роли нужно выбрать стол");
        return;
      }
    } else {
      table_id = null;
    }

    setBusy(true);
    try {
      await apiJson<User>("/api/admin/users", {
        method: "POST",
        body: JSON.stringify({
          username,
          password,
          role,
          table_id,
          is_active: !!newActive,
        }),
      });

      setNewUsername("");
      setNewPassword("");
      setNewRole("dealer");
      setNewTableId("");
      setNewActive(true);

      await loadUsersOnly();
      showOk("Пользователь создан");
    } catch (e: any) {
      setError(e?.message ?? "Ошибка создания пользователя");
    } finally {
      setBusy(false);
    }
  }

  async function saveUser(userId: number) {
    clearNotices();

    const role = draftRole[userId];
    const is_active = !!draftActive[userId];

    let table_id = draftTableId[userId] ? toInt(draftTableId[userId], 0) : null;
    const password = String(draftPassword[userId] ?? "");

    if (role !== "superadmin") {
      if (!table_id) {
        setError("Для этой роли нужно выбрать стол");
        return;
      }
    } else {
      table_id = null;
    }

    const body: any = {
      role,
      table_id,
      is_active,
    };

    if (isNonEmpty(password)) {
      if (password.length < 4) {
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
    } catch (e: any) {
      setError(e?.message ?? "Ошибка сохранения пользователя");
    } finally {
      setBusy(false);
    }
  }

  function setRoleForUser(userId: number, role: UserRole) {
    setDraftRole((prev) => ({ ...prev, [userId]: role }));
    if (role === "superadmin") {
      setDraftTableId((prev) => ({ ...prev, [userId]: "" }));
    }
  }

  function refreshCurrentTab() {
    if (tab === "tables") return loadTablesOnly();
    if (tab === "users") return loadUsersOnly();
    return loadPurchasesOnly();
  }

  if (!user) {
    return (
      <RequireAuth>
        <div className="p-4 text-white">Загрузка…</div>
      </RequireAuth>
    );
  }

  if (user.role !== "superadmin") {
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
              Столы, пользователи, покупки фишек
            </div>
          </div>

          <button
            className="rounded-xl bg-black text-white px-3 py-2 text-sm disabled:opacity-60"
            onClick={() => refreshCurrentTab().catch(() => {})}
            disabled={busy}
          >
            Обновить
          </button>
        </div>

        {error && (
          <div className="mb-3 rounded-xl bg-red-50 text-red-700 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        {ok && (
          <div className="mb-3 rounded-xl bg-green-50 text-green-800 px-3 py-2 text-sm">
            {ok}
          </div>
        )}

        <div className="flex gap-2 mb-3">
          <button
            className={
              "flex-1 rounded-xl px-4 py-3 text-left " +
              (tab === "tables"
                ? "bg-zinc-900 text-white"
                : "bg-black text-white/80 hover:text-white")
            }
            onClick={() => setTab("tables")}
          >
            <div className="font-semibold">Столы</div>
            <div className="text-xs text-white/60">создание и список</div>
          </button>

          <button
            className={
              "flex-1 rounded-xl px-4 py-3 text-left " +
              (tab === "users"
                ? "bg-zinc-900 text-white"
                : "bg-black text-white/80 hover:text-white")
            }
            onClick={() => setTab("users")}
          >
            <div className="font-semibold">Пользователи</div>
            <div className="text-xs text-white/60">роли, стол, пароль</div>
          </button>

          <button
            className={
              "flex-1 rounded-xl px-4 py-3 text-left " +
              (tab === "purchases"
                ? "bg-zinc-900 text-white"
                : "bg-black text-white/80 hover:text-white")
            }
            onClick={() => setTab("purchases")}
          >
            <div className="font-semibold">Покупки</div>
            <div className="text-xs text-white/60">последние операции</div>
          </button>
        </div>

        {tab === "tables" && (
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
                  min={1}
                  max={60}
                />

                <button
                  className="rounded-xl bg-green-600 text-white px-4 py-3 font-semibold disabled:opacity-60"
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
                      <div className="text-sm text-white/70">
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
                  placeholder="Пароль"
                  type="password"
                />

                <select
                  className={selectDark}
                  value={newRole}
                  onChange={(e) => {
                    const r = e.target.value as UserRole;
                    setNewRole(r);
                    if (r === "superadmin") setNewTableId("");
                  }}
                >
                  <option value="dealer">Дилер</option>
                  <option value="table_admin">Админ стола</option>
                  <option value="superadmin">Суперадмин</option>
                </select>

                <select
                  className={selectDark + " disabled:opacity-60"}
                  value={newTableId}
                  onChange={(e) => setNewTableId(e.target.value)}
                  disabled={newRole === "superadmin"}
                >
                  <option value="">
                    {newRole === "superadmin"
                      ? "Стол не требуется"
                      : "Выберите стол"}
                  </option>
                  {tables.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} (ID {t.id})
                    </option>
                  ))}
                </select>

                <label className="flex items-center gap-2 text-sm text-white/80">
                  <input
                    type="checkbox"
                    checked={newActive}
                    onChange={(e) => setNewActive(e.target.checked)}
                  />
                  Активен
                </label>

                <button
                  className="rounded-xl bg-green-600 text-white px-4 py-3 font-semibold disabled:opacity-60"
                  onClick={createUser}
                  disabled={
                    busy ||
                    !isNonEmpty(newUsername) ||
                    !isNonEmpty(newPassword) ||
                    (newRole !== "superadmin" && !isNonEmpty(newTableId))
                  }
                >
                  Создать
                </button>

                <div className="text-xs text-zinc-400">
                  Важно: на один стол допускается только один пользователь с
                  ролью “Админ стола”.
                </div>
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
                  {users.map((u) => {
                    const role = draftRole[u.id] ?? u.role;
                    const tableIdStr =
                      draftTableId[u.id] ??
                      (u.table_id == null ? "" : String(u.table_id));
                    const active = draftActive[u.id] ?? u.is_active;
                    const pwd = draftPassword[u.id] ?? "";

                    const t =
                      u.table_id != null ? tablesById.get(u.table_id) : null;

                    return (
                      <div
                        key={u.id}
                        className="rounded-xl bg-black text-white px-4 py-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="font-semibold">
                              {u.username}{" "}
                              <span className="text-xs text-white/60">
                                ID {u.id}
                              </span>
                            </div>
                            <div className="text-xs text-white/60">
                              Текущий стол:{" "}
                              {u.table_id == null
                                ? "—"
                                : t
                                ? `${t.name} (ID ${t.id})`
                                : `Стол ID ${u.table_id}`}
                            </div>
                            <div className="text-xs text-white/60">
                              Текущая роль: {roleLabel(u.role)}
                            </div>
                          </div>

                          <div
                            className={
                              "text-xs px-2 py-1 rounded-lg " +
                              (u.is_active
                                ? "bg-green-600/20 text-green-200"
                                : "bg-red-600/20 text-red-200")
                            }
                          >
                            {u.is_active ? "active" : "inactive"}
                          </div>
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
                            <option value="dealer">Дилер</option>
                            <option value="table_admin">Админ стола</option>
                            <option value="superadmin">Суперадмин</option>
                          </select>

                          <select
                            className={selectDark + " disabled:opacity-60"}
                            value={tableIdStr}
                            onChange={(e) =>
                              setDraftTableId((prev) => ({
                                ...prev,
                                [u.id]: e.target.value,
                              }))
                            }
                            disabled={busy || role === "superadmin"}
                          >
                            <option value="">
                              {role === "superadmin"
                                ? "Стол не требуется"
                                : "Выберите стол"}
                            </option>
                            {tables.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.name} (ID {t.id})
                              </option>
                            ))}
                          </select>

                          <label className="flex items-center gap-2 text-sm text-white/80">
                            <input
                              type="checkbox"
                              checked={!!active}
                              onChange={(e) =>
                                setDraftActive((prev) => ({
                                  ...prev,
                                  [u.id]: e.target.checked,
                                }))
                              }
                              disabled={busy}
                            />
                            Активен
                          </label>

                          <input
                            value={pwd}
                            onChange={(e) =>
                              setDraftPassword((prev) => ({
                                ...prev,
                                [u.id]: e.target.value,
                              }))
                            }
                            className={inputDark}
                            placeholder="Новый пароль (если нужно)"
                            type="password"
                            disabled={busy}
                          />

                          <button
                            className="rounded-xl bg-zinc-900 text-white px-4 py-3 font-semibold disabled:opacity-60"
                            onClick={() => saveUser(u.id)}
                            disabled={busy}
                          >
                            Сохранить изменения
                          </button>

                          <div className="text-xs text-white/60">
                            Если пользователь больше не работает — выключите
                            “Активен” или смените пароль.
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
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
                    min={1}
                    max={500}
                    placeholder="Лимит (например 100)"
                  />
                  <button
                    className="rounded-xl bg-green-600 text-white px-4 py-3 font-semibold disabled:opacity-60"
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

                      <div className="mt-1 text-sm text-white/80">
                        Место: <span className="text-white">{p.seat_no}</span> •
                        Сумма:{" "}
                        <span className="text-white font-semibold">
                          {p.amount}
                        </span>
                      </div>

                      <div className="mt-1 text-xs text-white/60">
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

// Вспомогательный тип, чтобы не ругался TS в createTable()
type TableOut = {
  id: number;
  name: string;
  seats_count: number;
};
