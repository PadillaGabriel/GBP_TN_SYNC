export class HttpError extends Error {
  constructor(message, { status = 0, payload = null } = {}) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.payload = payload;
  }
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.toLowerCase().includes("application/json")) {
    try {
      return await response.json();
    } catch (error) {
      throw new HttpError("El servidor devolvió JSON inválido.", {
        status: response.status,
        payload: { detalle: error.message },
      });
    }
  }

  const text = await response.text();
  return text ? { detalle: text } : {};
}

export async function request(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await parseResponse(response);

  if (!response.ok) {
    const message =
      payload?.detail ||
      payload?.detalle ||
      payload?.error ||
      payload?.message ||
      `Error HTTP ${response.status}`;
    throw new HttpError(String(message), { status: response.status, payload });
  }
  return payload;
}

export function errorMessage(error) {
  if (error instanceof HttpError && error.payload) {
    return (
      error.payload.detail ||
      error.payload.detalle ||
      error.payload.error ||
      error.payload.message ||
      error.message
    );
  }
  return error instanceof Error ? error.message : String(error);
}
