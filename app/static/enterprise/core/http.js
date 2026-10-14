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

function messageFromPayload(payload) {
  if (typeof payload === "string") return payload;
  if (Array.isArray(payload)) {
    return payload.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
        const message = item.msg || item.message || "Solicitud inválida";
        return field ? `${field}: ${message}` : String(message);
      }
      return "Solicitud inválida";
    }).join("; ");
  }
  if (payload && typeof payload === "object") {
    return messageFromPayload(payload.detail ?? payload.detalle ?? payload.error ?? payload.message);
  }
  return "";
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
    const message = messageFromPayload(payload) || `Error HTTP ${response.status}`;
    throw new HttpError(String(message), { status: response.status, payload });
  }
  return payload;
}

export function errorMessage(error) {
  if (error instanceof HttpError) {
    return messageFromPayload(error.payload) || error.message;
  }
  return error instanceof Error ? error.message : String(error);
}
