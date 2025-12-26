import { NextResponse } from "next/server";

const API_BASE =
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://127.0.0.1:8000";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const target = new URL("/api/admin/export" + url.search, API_BASE);

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

  const outHeaders = new Headers(res.headers);
  outHeaders.delete("content-encoding");

  return new NextResponse(res.body, {
    status: res.status,
    headers: outHeaders,
  });
}
