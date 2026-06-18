const form = document.getElementById("run-form");
const submitBtn = document.getElementById("submitBtn");
const statusEl = document.getElementById("status");
const resultTextEl = document.getElementById("resultText");
const checksEl = document.getElementById("checks");
const rawJsonEl = document.getElementById("rawJson");
const resultFilesEl = document.getElementById("resultFiles");

function setStatus(text) {
  statusEl.textContent = text;
}

function toPrettyJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch (err) {
    return String(value);
  }
}

function normalizeStoragePath(path) {
  if (!path || typeof path !== "string") return "";
  const unix = path.replace(/\\/g, "/");
  const marker = "/storage/";
  const idx = unix.indexOf(marker);
  if (idx >= 0) return unix.slice(idx);
  if (unix.startsWith("storage/")) return `/${unix}`;
  return "";
}

function renderFiles(files) {
  resultFilesEl.innerHTML = "";
  if (!Array.isArray(files) || files.length === 0) {
    const li = document.createElement("li");
    li.textContent = "无输出文件";
    resultFilesEl.appendChild(li);
    return;
  }

  files.forEach((item, index) => {
    const li = document.createElement("li");
    const path = item && item.path ? String(item.path) : "";
    const normalized = normalizeStoragePath(path);
    const name = (item && item.filename) || `output_${index + 1}`;

    if (normalized) {
      const a = document.createElement("a");
      a.href = normalized;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = `${name} (${normalized})`;
      li.appendChild(a);
    } else {
      li.textContent = `${name} (${path || "unknown path"})`;
    }

    resultFilesEl.appendChild(li);
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  submitBtn.disabled = true;
  setStatus("提交中...");
  resultTextEl.textContent = "处理中...";
  checksEl.textContent = "处理中...";
  rawJsonEl.textContent = "处理中...";
  resultFilesEl.innerHTML = "";

  const prompt = document.getElementById("prompt").value.trim();
  const filesInput = document.getElementById("files");
  const taskType = document.getElementById("taskType").value || "auto";
  const outputMode = document.getElementById("outputMode").value || "full";

  const formData = new FormData();
  formData.append("prompt", prompt);

  const files = filesInput.files || [];
  for (const file of files) {
    formData.append("files", file, file.name);
  }

  formData.append("capabilities", JSON.stringify({ allow_fallback: true }));
  formData.append("output_mode", outputMode);
  formData.append("task_type", taskType);
  formData.append("infer_task_type", "true");
  formData.append("include_execution_logs", "true");

  try {
    const resp = await fetch("/api/agent/run", {
      method: "POST",
      body: formData,
    });

    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data && data.detail ? data.detail : `HTTP ${resp.status}`);
    }

    const structured = data.structured_data || {};
    const checks = structured.checks || {};
    const issues = structured.issues || [];
    const resultText = data.result_text || data.answer || "";

    resultTextEl.textContent = resultText || "(空)";
    checksEl.textContent = toPrettyJson({ success: data.success, checks, issues });
    rawJsonEl.textContent = toPrettyJson(data);
    renderFiles(data.result_files || []);
    setStatus(data.success ? "完成" : "执行完成但未通过");
  } catch (err) {
    const message = err && err.message ? err.message : String(err);
    resultTextEl.textContent = `请求失败: ${message}`;
    checksEl.textContent = "(无)";
    rawJsonEl.textContent = "(无)";
    renderFiles([]);
    setStatus("失败");
  } finally {
    submitBtn.disabled = false;
  }
});
