"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/AuthContext";
import type { UserRole } from "@/lib/types";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setErr(null);
    setBusy(true);

    try {
      const u = await login(username.trim(), password);

      const role: UserRole = u.role;

      if (role === "superadmin") {
        router.replace("/admin");
        return;
      }

      if (role === "table_admin") {
        router.replace("/admin/export");
        return;
      }

      router.replace("/");
    } catch (e: any) {
      setErr(e?.message ?? "Ошибка авторизации");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="p-4 max-w-md mx-auto">
      <div className="text-2xl font-bold text-white mb-2 drop-shadow">Вход</div>

      <div className="text-sm text-zinc-400 mb-4">Введите логин и пароль.</div>

      {err && (
        <div className="mb-3 rounded-xl bg-red-50 text-red-700 px-3 py-2 text-sm">
          {err}
        </div>
      )}

      <div className="grid gap-2">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="rounded-xl border px-3 py-3 text-base text-black placeholder-zinc-600"
          placeholder="Логин"
          autoComplete="username"
        />

        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-xl border px-3 py-3 text-base text-black placeholder-zinc-600"
          placeholder="Пароль"
          type="password"
          autoComplete="current-password"
        />

        <button
          className="rounded-xl bg-black text-white px-4 py-3 font-semibold disabled:opacity-60"
          disabled={busy || !username.trim() || !password}
          onClick={submit}
        >
          {busy ? "Входим..." : "Войти"}
        </button>

        <div className="text-xs text-zinc-500 mt-3">
          По умолчанию (первый запуск):{" "}
          <span className="text-white font-semibold">admin / admin</span>
        </div>
      </div>
    </main>
  );
}
