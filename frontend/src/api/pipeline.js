import axios from "axios";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = axios.create({ baseURL: BASE });

/**
 * Parse a JD PDF — returns extracted text string.
 * @param {File}   file
 * @param {string} token  Clerk JWT from useAuth().getToken()
 */
export async function parseJdPdf(file, token) {
  const form = new FormData();
  form.append("jd_pdf", file); // must match FastAPI field name
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await api.post("/parse-jd", form, { headers });
  return res.data.extracted_text;
}

/**
 * Run the full HireGraph pipeline.
 * @param {string}   jobDescription  Raw JD text
 * @param {File[]}   resumeFiles     Array of PDF File objects
 * @param {string}   token           Clerk JWT from useAuth().getToken()
 * @param {string}   [teamData]      Optional team CSV/JSON string
 */
export async function runPipeline(jobDescription, resumeFiles, token, teamData = "") {
  const form = new FormData();
  form.append("jd_text", jobDescription);
  resumeFiles.forEach((f) => form.append("resumes", f));
  if (teamData && teamData.trim()) {
    form.append("team_data", teamData);
  }

  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await api.post("/run/text", form, {
    headers,
    timeout: 300_000,
  });
  return res.data;
}

/**
 * Stream the pipeline via SSE.
 * Calls onEvent(eventType, parsedData) for each SSE event.
 * Event types: 'agent_update', 'pipeline_complete', 'error'
 *
 * @param {string}   jobDescription
 * @param {File[]}   resumeFiles
 * @param {string}   token
 * @param {string}   teamData
 * @param {Function} onEvent   (type: string, data: object) => void
 */
export async function streamPipeline(jobDescription, resumeFiles, token, teamData = "", onEvent) {
  const form = new FormData();
  form.append("jd_text", jobDescription);
  resumeFiles.forEach((f) => form.append("resumes", f));
  if (teamData && teamData.trim()) form.append("team_data", teamData);

  const headers = { "Accept": "text/event-stream" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${BASE}/run/stream`, {
    method: "POST",
    headers,
    body: form,
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(err || `HTTP ${response.status}`);
  }

  const reader  = response.body.getReader();
  const decoder = new TextDecoder();
  let   buffer  = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE blocks are separated by double newlines
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop(); // keep incomplete trailing block

    for (const block of blocks) {
      if (!block.trim() || block.startsWith(":")) continue; // skip keepalives/comments

      let eventType = "message";
      let eventData = "";

      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        if (line.startsWith("data: "))  eventData  = line.slice(6).trim();
      }

      if (eventData) {
        try { onEvent(eventType, JSON.parse(eventData)); }
        catch (e) { console.warn("SSE parse error", e, eventData); }
      }
    }
  }
}
