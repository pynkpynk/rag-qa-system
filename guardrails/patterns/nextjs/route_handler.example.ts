import { NextResponse } from "next/server";

/**
 * Prefer Route Handlers for a stable HTTP API boundary:
 * - external clients
 * - webhooks
 * - explicit HTTP caching/status
 */
export async function POST(req: Request) {
  const body = (await req.json()) as { title?: string };

  if (!body.title?.trim()) {
    return NextResponse.json(
      { error: { code: "validation.title_required", message: "Title is required." } },
      { status: 400 }
    );
  }

  // TODO: perform mutation
  return NextResponse.json({ ok: true }, { status: 200 });
}
