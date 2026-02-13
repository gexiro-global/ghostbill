import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://backend:8000";

async function proxyRequest(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  const { path } = await params;
  const targetPath = `/v1/${path.join("/")}`;
  const url = `${BACKEND_URL}${targetPath}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "host" && key.toLowerCase() !== "connection") {
      headers.set(key, value);
    }
  });

  const init: RequestInit = {
    method: request.method,
    headers,
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    try {
      const body = await request.text();
      if (body) {
        init.body = body;
      }
    } catch {
      // No body
    }
  }

  try {
    const response = await fetch(url, init);
    const data = await response.text();

    return new NextResponse(data, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") || "application/json",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { detail: "Backend unavailable" },
      { status: 502 }
    );
  }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, context);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, context);
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, context);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, context);
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, context);
}
