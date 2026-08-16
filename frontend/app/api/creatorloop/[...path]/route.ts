import { NextRequest, NextResponse } from "next/server";

const ALLOWED = [
  /^channels\/current$/,
  /^channels\/\d+\/sync-status$/,
  /^channels\/connect$/,
  /^channels\/sync$/,
  /^dashboard\/summary$/,
  /^comments$/,
  /^comments\/\d+$/,
  /^replies$/,
  /^replies\/\d+$/,
  /^replies\/\d+\/(approve|ignore)$/,
  /^opportunities$/,
  /^opportunities\/\d+$/,
  /^opportunities\/\d+\/brief$/,
  /^videos$/,
  /^videos\/\d+$/,
  /^settings\/public$/,
];

const SECRET_REQUIRED = [
  /^channels\/connect$/,
  /^channels\/sync$/,
  /^replies\/\d+\/(approve|ignore)$/,
];

function isAllowed(path: string): boolean {
  return ALLOWED.some((pattern) => pattern.test(path));
}

function needsSecret(path: string, method: string): boolean {
  return method !== "GET" && SECRET_REQUIRED.some((pattern) => pattern.test(path));
}

async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path: parts } = await context.params;
  const path = parts.join("/");

  if (!isAllowed(path)) {
    return NextResponse.json({ detail: { code: "frontend_proxy_denied", message: "This API route is not exposed by the CreatorLoop frontend." } }, { status: 404 });
  }

  const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");
  if (!baseUrl) {
    return NextResponse.json({ detail: { code: "backend_not_configured", message: "NEXT_PUBLIC_API_BASE_URL is not configured." } }, { status: 503 });
  }

  const url = new URL(`${baseUrl}/api/${path}`);
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.append(key, value));

  const headers = new Headers({ Accept: "application/json" });
  if (request.headers.get("content-type")) headers.set("Content-Type", request.headers.get("content-type")!);

  if (needsSecret(path, request.method)) {
    const secret = process.env.FASTAPI_INTERNAL_API_KEY;
    if (!secret) {
      return NextResponse.json({ detail: { code: "internal_key_missing", message: "FASTAPI_INTERNAL_API_KEY is not configured on Vercel." } }, { status: 503 });
    }
    headers.set("X-Internal-API-Key", secret);
  }

  let body: string | undefined;
  if (!["GET", "HEAD"].includes(request.method)) {
    body = await request.text();
  }

  try {
    const upstream = await fetch(url, {
      method: request.method,
      headers,
      body: body || undefined,
      cache: "no-store",
    });

    const text = await upstream.text();
    return new NextResponse(text || null, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json({ detail: { code: "backend_unreachable", message: "CreatorLoop backend is unreachable." } }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
