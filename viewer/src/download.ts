// A download with its progress (a run's data.js, the 3D view's patch) by XMLHttpRequest, not a fetch's streamed
// body: its progress events count the body's bytes as they come, after any decompression, and headless Edge's
// virtual time (the tests' --dump-dom) waits for it as for a script, while it runs ahead of a fetch's stream
// (with no timer left it jumps to its budget's end, and the page never sees the data).

/** web.SIZE_HEADER: a run's script's bytes before compression (nginx gzips it on the fly and drops
 *  Content-Length). */
export const SIZE_HEADER = "X-Findaline-Bytes";
const REPORT_MS = 100;  // the progress at most this often (each report may draw the page again)

/** The bytes the body will have as read: SIZE_HEADER, else Content-Length when nothing compressed it (a
 *  compressed body reads as more bytes than it says); null when unknown. `header` gives a header's value. */
export function bodySize(header: (name: string) => string | null): number | null {
  const given = Number(header(SIZE_HEADER) ?? NaN);
  if (Number.isFinite(given) && given > 0) return given;
  const length = Number(header("content-length") ?? NaN);
  return !header("content-encoding") && Number.isFinite(length) && length > 0 ? length : null;
}

export interface DownloadOptions {
  headers?: Record<string, string>;
  /** The answer's headers are in: the body's size when known (bodySize). */
  onHeaders?(total: number | null): void;
  /** Bytes of the body read so far, of `total`; at most every REPORT_MS. */
  onBytes?(done: number, total: number | null): void;
}

export interface Answer<T> {
  status: number;
  body: T;
  /** The bytes of the body as read. */
  bytes: number;
  header(name: string): string | null;
}

/** GET `url` as text or bytes; rejects on a network error only (the caller checks `status`). */
export function download(url: string, type: "text", options?: DownloadOptions): Promise<Answer<string>>;
export function download(url: string, type: "arraybuffer", options?: DownloadOptions): Promise<Answer<ArrayBuffer>>;
export function download(url: string, type: "text" | "arraybuffer", options: DownloadOptions = {}): Promise<Answer<any>> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("GET", url);
    xhr.responseType = type;
    for (const [name, value] of Object.entries(options.headers ?? {})) xhr.setRequestHeader(name, value);
    let total: number | null = null, reported = 0;
    const header = (name: string) => xhr.getResponseHeader(name);
    xhr.onreadystatechange = () => {
      if (xhr.readyState !== XMLHttpRequest.HEADERS_RECEIVED) return;
      total = bodySize(header);
      options.onHeaders?.(total);
    };
    xhr.onprogress = (e) => {
      const now = performance.now();
      if (now - reported < REPORT_MS) return;
      reported = now;
      options.onBytes?.(e.loaded, total);
    };
    xhr.onload = (e) => {
      options.onBytes?.(e.loaded, total);
      resolve({status: xhr.status, body: xhr.response, bytes: e.loaded, header});
    };
    xhr.onerror = () => reject(new Error("the download of " + url + " failed"));
    xhr.onabort = () => reject(new Error("the download of " + url + " was stopped"));
    xhr.send();
  });
}
