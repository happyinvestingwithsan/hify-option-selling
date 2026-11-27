/**
 * Dynamic backend API client for local and Tailscale access.
 * Resolves to NEXT_PUBLIC_API_URL if set, otherwise http://<window.location.hostname>:8000
 * in the browser (so Tailscale mobile access automatically targets the host laptop :8000),
 * or http://127.0.0.1:8000 during SSR.
 */

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (configured) {
    return configured.replace(/\/+$/, "");
  }

  if (typeof window !== "undefined" && window.location?.hostname) {
    const protocol = window.location.protocol === "https:" ? "https:" : "http:";
    return `${protocol}//${window.location.hostname}:8000`;
  }

  return "http://127.0.0.1:8000";
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${getApiBaseUrl()}${normalizedPath}`;

  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...options,
    headers,
    cache: options.cache ?? "no-store",
  });

  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");

  if (!response.ok) {
    let message = `Request failed (${response.status} ${response.statusText})`;
    let detail: unknown = undefined;

    if (isJson) {
      try {
        const body = (await response.json()) as Record<string, unknown>;
        detail = body.detail ?? body;
        if (typeof body.detail === "string" && body.detail.trim()) {
          message = body.detail;
        } else if (typeof body.message === "string" && body.message.trim()) {
          message = body.message;
        } else if (body.detail && typeof body.detail === "object") {
          const nested = body.detail as Record<string, unknown>;
          if (typeof nested.message === "string") {
            message = nested.message;
          } else if (typeof nested.reason === "string") {
            message = nested.reason;
          }
        }
      } catch {
        // Keep fallback HTTP status message if JSON parsing fails
      }
    } else {
      try {
        const text = (await response.text()).trim();
        if (text) {
          message = text;
        }
      } catch {
        // Keep fallback HTTP status message
      }
    }

    throw new ApiError(message, response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  if (isJson) {
    return (await response.json()) as T;
  }

  return (await response.text()) as unknown as T;
}
