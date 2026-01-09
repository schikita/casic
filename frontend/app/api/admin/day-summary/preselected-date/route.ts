import { NextResponse } from "next/server";

const API_BASE =
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://127.0.0.1:8000";

export async function GET(request: Request) {
  const target = new URL("/api/admin/day-summary/preselected-date", API_BASE);

  const headers = new Headers();

  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);

  const authorization = request.headers.get("authorization");
  if (authorization) headers.set("authorization", authorization);

  const res = await fetch(target.toString(), {
    method: "GET",
    headers,
    cache: "no-store",
  });

  return NextResponse.json(await res.json(), { status: res.status });
}
