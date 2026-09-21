const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
let authRedirecting = false;

export function getToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("sillage_token");
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (response.status === 401 && path !== "/auth/login" && typeof window !== "undefined") {
    localStorage.removeItem("sillage_token");
    if (!authRedirecting) {
      authRedirecting = true;
      window.location.replace("/");
    }
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: "Une erreur est survenue" }));
    // FastAPI renvoie une liste d'erreurs quand la validation du corps echoue.
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item: { msg?: string }) => item.msg?.replace("Value error, ", "")).filter(Boolean).join(" · ")
      : data.detail;
    throw new Error(detail || "Une erreur est survenue");
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export { API_URL };
