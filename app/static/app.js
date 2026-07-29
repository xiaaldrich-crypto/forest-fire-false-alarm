const HISTORY_KEY = "forestguard_history_v1";
const MAX_HISTORY = 12;

const form = document.getElementById("form");
const result = document.getElementById("result");
const resultEmpty = document.getElementById("resultEmpty");
const decisionEl = document.getElementById("decision");
const reasonEl = document.getElementById("reason");
const jsonEl = document.getElementById("json");
const batchBtn = document.getElementById("batchBtn");
const batchMsg = document.getElementById("batchMsg");
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file");
const fileLabel = document.getElementById("fileLabel");
const dzBody = document.getElementById("dzBody");
const previewWrap = document.getElementById("previewWrap");
const previewImg = document.getElementById("previewImg");
const previewVideo = document.getElementById("previewVideo");
const previewName = document.getElementById("previewName");
const submitBtn = document.getElementById("submitBtn");
const btnLabel = submitBtn.querySelector(".btn-label");
const btnSpin = submitBtn.querySelector(".btn-spin");
const pipeline = document.getElementById("pipeline");
const mediaTag = document.getElementById("mediaTag");
const confTag = document.getElementById("confTag");
const jobTag = document.getElementById("jobTag");
const typeTag = document.getElementById("typeTag");
const resultHint = document.getElementById("resultHint");
const clockEl = document.getElementById("clock");
const gaugeList = document.getElementById("gaugeList");
const chainList = document.getElementById("chainList");
const stageImg = document.getElementById("stageImg");
const stageVideo = document.getElementById("stageVideo");
const thumbStrip = document.getElementById("thumbStrip");
const galleryTabs = document.getElementById("galleryTabs");
const historyList = document.getElementById("historyList");
const historyEmpty = document.getElementById("historyEmpty");
const outputDeck = document.getElementById("outputDeck");
const lightbox = document.getElementById("lightbox");
const lbImg = document.getElementById("lbImg");
const processBoard = document.getElementById("processBoard");
const processBar = document.getElementById("processBar");
const processPct = document.getElementById("processPct");
const processTitle = document.getElementById("processTitle");
const processNote = document.getElementById("processNote");
const processSteps = document.getElementById("processSteps");
const fullVideoPanel = document.getElementById("fullVideoPanel");
const fullVideo = document.getElementById("fullVideo");
const playFullBtn = document.getElementById("playFullBtn");
const downloadVideo = document.getElementById("downloadVideo");
const videoTimeLabel = document.getElementById("videoTimeLabel");
const videoSourceLabel = document.getElementById("videoSourceLabel");
const seekBackBtn = document.getElementById("seekBackBtn");
const seekFwdBtn = document.getElementById("seekFwdBtn");

let currentLayers = {};
let activeLayer = "origin";
let currentData = null;
let processTimer = null;
/** 本地上传文件的 Object URL，优先用于可拖动的完整视频播放 */
let localMediaUrl = null;
let localMediaIsVideo = false;

function tickClock() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  clockEl.textContent = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
tickClock();
setInterval(tickClock, 1000);

function setPipeline(mode) {
  const steps = [...pipeline.querySelectorAll(".step")];
  steps.forEach((el) => el.classList.remove("active", "done"));
  clearInterval(setPipeline._timer);
  if (mode === "idle") return;
  if (mode === "running") {
    let i = 0;
    const run = () => {
      steps.forEach((el, idx) => {
        el.classList.toggle("done", idx < i);
        el.classList.toggle("active", idx === i);
      });
      i = Math.min(i + 1, steps.length - 1);
    };
    run();
    setPipeline._timer = setInterval(run, 650);
    return;
  }
  steps.forEach((el) => el.classList.add("done"));
}

function showProcess(isVideo) {
  resultEmpty.hidden = true;
  result.hidden = true;
  processBoard.hidden = false;
  processTitle.textContent = isVideo ? "视频二次判别进行中…" : "图片二次判别进行中…";
  processNote.textContent = isVideo
    ? "正在抽帧、提取火烟特征并调用多模态，请稍候"
    : "正在提取特征、规则初判与多模态复核";
  resultHint.textContent = "判别过程进行中…";

  const ids = ["opencv", "rules", "llm", "merge"];
  let step = 0;
  let pct = 6;
  const paint = () => {
    pct = Math.min(pct + (isVideo ? 3 : 5), 92);
    processBar.style.width = `${pct}%`;
    processPct.textContent = `${Math.round(pct)}%`;
    [...processSteps.querySelectorAll("li")].forEach((li, idx) => {
      li.classList.toggle("done", idx < step);
      li.classList.toggle("active", idx === step);
    });
  };
  paint();
  clearInterval(processTimer);
  processTimer = setInterval(() => {
    if (step < ids.length - 1 && pct > (step + 1) * 20) step += 1;
    paint();
  }, isVideo ? 900 : 550);
}

function hideProcess() {
  clearInterval(processTimer);
  processTimer = null;
  processBoard.hidden = true;
  processBar.style.width = "100%";
  processPct.textContent = "100%";
  [...processSteps.querySelectorAll("li")].forEach((li) => {
    li.classList.add("done");
    li.classList.remove("active");
  });
}

function fmtClock(sec) {
  if (!Number.isFinite(sec) || sec < 0) return "00:00";
  const s = Math.floor(sec % 60);
  const m = Math.floor(sec / 60) % 60;
  const h = Math.floor(sec / 3600);
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function updateVideoTime() {
  if (!videoTimeLabel) return;
  videoTimeLabel.textContent = `${fmtClock(fullVideo.currentTime)} / ${fmtClock(fullVideo.duration)}`;
}

function setVideoSource(el, url) {
  if (!el || !url) return;
  const abs = new URL(url, location.href).href;
  if (el.src !== abs) {
    el.src = url;
    el.load();
  }
}

function bindFullVideo(data, opts = {}) {
  const isVideo = Boolean(data.is_video || data.media_type === "video");
  if (!isVideo) {
    fullVideoPanel.hidden = true;
    fullVideo.removeAttribute("src");
    try {
      fullVideo.load();
    } catch (_) {}
    return;
  }

  const preferLocal = opts.preferLocal !== false;
  const src =
    preferLocal && localMediaUrl && localMediaIsVideo
      ? localMediaUrl
      : data.upload_url;
  if (!src) {
    fullVideoPanel.hidden = true;
    return;
  }

  fullVideoPanel.hidden = false;
  setVideoSource(fullVideo, src);
  downloadVideo.href = data.upload_url || src;
  const name = data.media_name || data.image_name || "alarm.mp4";
  downloadVideo.setAttribute("download", name);
  const usingLocal = preferLocal && localMediaUrl && localMediaIsVideo && src === localMediaUrl;
  videoSourceLabel.textContent = usingLocal
    ? "播放源：本地上传文件（可完整拖动）"
    : "播放源：服务器文件（已优化进度条）";

  fullVideo.onloadedmetadata = updateVideoTime;
  fullVideo.ontimeupdate = updateVideoTime;
  fullVideo.onerror = () => {
    if (usingLocal && data.upload_url) {
      videoSourceLabel.textContent = "本地播放失败，已切换服务器文件";
      setVideoSource(fullVideo, data.upload_url);
    } else {
      videoSourceLabel.textContent = "视频无法播放，请尝试下载后用本地播放器打开";
    }
  };
}


function paintDecision(text, loading = false) {
  decisionEl.textContent = text;
  decisionEl.className = "decision";
  if (loading) decisionEl.classList.add("loading");
  else if (text.includes("真实火情")) decisionEl.classList.add("fire");
  else if (text.includes("误报")) decisionEl.classList.add("false");
  else decisionEl.classList.add("review");
}

function fmtPct(v) {
  if (v == null || Number.isNaN(Number(v))) return null;
  return Math.max(0, Math.min(1, Number(v)));
}

function decisionClass(text) {
  if ((text || "").includes("真实火情")) return "fire";
  if ((text || "").includes("误报")) return "false";
  return "review";
}

function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveHistory(list) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, MAX_HISTORY)));
}

function pushHistory(data) {
  const o = data.opencv || {};
  const thumb =
    o.vis_overlay_path || o.keyframe_path || data.upload_url || "";
  const item = {
    id: data.job_id || String(Date.now()),
    name: data.media_name || data.image_name || "未命名",
    decision: data.final_decision,
    time: new Date().toLocaleString("zh-CN", { hour12: false }),
    thumb,
    payload: data,
  };
  const list = loadHistory().filter((x) => x.id !== item.id);
  list.unshift(item);
  saveHistory(list);
  renderHistory(item.id);
}

function renderHistory(activeId) {
  const list = loadHistory();
  historyList.innerHTML = "";
  historyEmpty.hidden = list.length > 0;
  list.forEach((item) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "hist-item" + (item.id === activeId ? " active" : "");
    const cls = decisionClass(item.decision);
    const thumbHtml = item.thumb
      ? `<img class="hist-thumb" src="${item.thumb}" alt="" />`
      : `<div class="hist-thumb ph">N/A</div>`;
    btn.innerHTML = `${thumbHtml}<div class="hist-meta"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.time)}</span><span class="hist-badge ${cls}">${escapeHtml(item.decision || "—")}</span></div>`;
    btn.addEventListener("click", () => {
      renderResult(item.payload, { fromHistory: true });
      renderHistory(item.id);
    });
    li.appendChild(btn);
    historyList.appendChild(li);
  });
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function buildLayers(data, opts = {}) {
  const o = data.opencv || {};
  const isVideo = Boolean(data.is_video || data.media_type === "video");
  const preferLocal = opts.preferLocal !== false;
  const originUrl =
    isVideo && preferLocal && localMediaUrl && localMediaIsVideo
      ? localMediaUrl
      : data.upload_url;
  return {
    origin: {
      label: isVideo ? "原视频" : "原图",
      url: originUrl,
      video: isVideo,
    },
    keyframe: { label: "关键帧", url: o.keyframe_path || data.upload_url, video: false },
    fire: { label: "火焰掩膜", url: o.vis_fire_path, video: false },
    smoke: { label: "烟雾掩膜", url: o.vis_smoke_path, video: false },
    overlay: {
      label: "叠加结果",
      url: o.vis_overlay_path || o.keyframe_path || data.upload_url,
      video: false,
    },
  };
}

function setActiveLayer(key) {
  activeLayer = key;
  const layer = currentLayers[key];
  [...galleryTabs.querySelectorAll(".tab")].forEach((t) => {
    t.classList.toggle("active", t.dataset.layer === key);
  });
  [...thumbStrip.querySelectorAll(".thumb")].forEach((t) => {
    t.classList.toggle("active", t.dataset.layer === key);
  });
  if (!layer || !layer.url) {
    try {
      stageVideo.pause();
    } catch (_) {}
    stageVideo.hidden = true;
    stageVideo.removeAttribute("src");
    stageImg.hidden = false;
    stageImg.removeAttribute("src");
    stageImg.alt = "暂无该图层";
    return;
  }
  if (layer.video) {
    stageImg.hidden = true;
    stageImg.removeAttribute("src");
    stageVideo.hidden = false;
    setVideoSource(stageVideo, layer.url);
  } else {
    try {
      stageVideo.pause();
    } catch (_) {}
    stageVideo.hidden = true;
    stageVideo.removeAttribute("src");
    stageImg.hidden = false;
    stageImg.src = layer.url;
  }
}

function renderThumbs() {
  thumbStrip.innerHTML = "";
  Object.entries(currentLayers).forEach(([key, layer]) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "thumb" + (layer.url ? "" : " disabled");
    btn.dataset.layer = key;
    if (layer.url && !layer.video) {
      btn.innerHTML = `<img src="${layer.url}" alt="" /><span class="cap">${layer.label}</span>`;
    } else if (layer.url && layer.video) {
      btn.innerHTML = `<div class="hist-thumb ph" style="width:100%;height:100%;border-radius:0">VIDEO</div><span class="cap">${layer.label}</span>`;
    } else {
      btn.innerHTML = `<div class="hist-thumb ph" style="width:100%;height:100%;border-radius:0">无</div><span class="cap">${layer.label}</span>`;
    }
    if (layer.url) {
      btn.addEventListener("click", () => setActiveLayer(key));
    }
    thumbStrip.appendChild(btn);
  });
}

function renderGauges(data) {
  const o = data.opencv || {};
  const items = [
    { k: "火焰面积比", v: fmtPct(o.fire_area_ratio), cls: "fire" },
    { k: "烟雾面积比", v: fmtPct(o.smoke_area_ratio), cls: "smoke" },
    { k: "烟柱形态分", v: fmtPct(o.smoke_plume_score), cls: "" },
    { k: "火焰持续性", v: fmtPct(o.fire_persistence), cls: "fire" },
    { k: "烟雾持续性", v: fmtPct(o.smoke_persistence), cls: "smoke" },
    { k: "高亮占比", v: fmtPct(o.bright_ratio), cls: "" },
  ];
  gaugeList.innerHTML = items
    .map((it) => {
      const pct = it.v == null ? 0 : it.v;
      const label = it.v == null ? "—" : `${(pct * 100).toFixed(1)}%`;
      return `<div class="gauge"><div class="gauge-top"><span>${it.k}</span><em>${label}</em></div><div class="bar ${it.cls}"><i style="width:${pct * 100}%"></i></div></div>`;
    })
    .join("");
  // trigger reflow for animation
  requestAnimationFrame(() => {
    gaugeList.querySelectorAll(".bar > i").forEach((el) => {
      const w = el.style.width;
      el.style.width = "0";
      requestAnimationFrame(() => {
        el.style.width = w;
      });
    });
  });
}

function renderChain(data) {
  const rules = data.rules || {};
  const mm = data.multimodal || {};
  const o = data.opencv || {};
  const scores = (rules.scores || [])
    .slice()
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 3);

  const mmStatus = mm.degraded
    ? "调用降级"
    : mm.enabled
      ? "已启用"
      : "未启用";
  const mmDec =
    (mm.raw && mm.raw.decision) ||
    (mm.is_real_fire === true
      ? "疑似真实火情"
      : mm.is_real_fire === false
        ? "疑似误报"
        : "—");

  const fireP = fmtPct(o.fire_area_ratio);
  const smokeP = fmtPct(o.smoke_area_ratio);
  const steps = [
    {
      title: "OpenCV 特征提取",
      body: `火焰 ${fireP == null ? "—" : (fireP * 100).toFixed(1) + "%"} · 烟雾 ${smokeP == null ? "—" : (smokeP * 100).toFixed(1) + "%"} · 抽帧 ${o.sampled_frames || o.frame_count || 1}`,
    },
    {
      title: `规则初判 · ${rules.preliminary_decision || "—"}`,
      body: rules.top_type ? `Top 类型：${rules.top_type}` : "无主导误报类型",
      scores,
    },
    {
      title: `多模态复核 · ${mmStatus}`,
      body: `${mmDec}${mm.false_alarm_type ? ` · ${mm.false_alarm_type}` : ""}${mm.reason ? ` — ${mm.reason}` : ""}`,
    },
    {
      title: `融合决策 · ${data.final_decision || "—"}`,
      body: data.final_reason || "",
    },
  ];

  chainList.innerHTML = steps
    .map((s, i) => {
      let extra = "";
      if (s.scores?.length) {
        extra = `<div class="score-mini">${s.scores
          .map((sc) => {
            const p = Math.max(0, Math.min(1, Number(sc.score) || 0));
            return `<div><span>${escapeHtml(sc.type)}</span><span>${(p * 100).toFixed(0)}</span></div><div class="mini-bar"><i style="width:${p * 100}%"></i></div>`;
          })
          .join("")}</div>`;
      }
      return `<li class="chain-item" data-n="${i + 1}"><strong>${escapeHtml(s.title)}</strong><p>${escapeHtml(s.body)}</p>${extra}</li>`;
    })
    .join("");
}

function renderResult(data, opts = {}) {
  currentData = data;
  hideProcess();
  resultEmpty.hidden = true;
  processBoard.hidden = true;
  result.hidden = false;

  paintDecision(data.final_decision || "—");
  reasonEl.textContent = data.final_reason || "";
  mediaTag.textContent =
    data.is_video || data.media_type === "video" ? "视频" : "图片";
  const conf = data.multimodal?.confidence;
  confTag.textContent =
    conf == null || conf === "" ? "—" : `${(Number(conf) * 100).toFixed(0)}%`;
  jobTag.textContent = data.job_id || "—";
  typeTag.textContent =
    data.multimodal?.false_alarm_type || data.rules?.top_type || "—";

  currentLayers = buildLayers(data, { preferLocal: !opts.fromHistory });
  renderThumbs();
  const isVideo = Boolean(data.is_video || data.media_type === "video");
  const prefer = isVideo
    ? "origin"
    : currentLayers.overlay?.url
      ? "overlay"
      : currentLayers.keyframe?.url
        ? "keyframe"
        : "origin";
  bindFullVideo(data, { preferLocal: !opts.fromHistory });
  setActiveLayer(prefer);
  renderGauges(data);
  renderChain(data);
  jsonEl.textContent = JSON.stringify(data, null, 2);
  resultHint.textContent = opts.fromHistory
    ? `回看任务 ${data.job_id || ""}`
    : `任务完成 · ${data.job_id || ""}`;

  outputDeck.classList.remove("flash");
  void outputDeck.offsetWidth;
  outputDeck.classList.add("flash");
  if (!opts.fromHistory) {
    outputDeck.scrollIntoView({ behavior: "smooth", block: "start" });
    if (isVideo) {
      setTimeout(() => {
        fullVideoPanel.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 200);
    }
  }
}

function setLoading(on) {
  submitBtn.disabled = on;
  btnSpin.hidden = !on;
  btnLabel.textContent = on ? "判别中…" : "启动二次判别";
}

function showLocalPreview(file) {
  if (localMediaUrl) {
    URL.revokeObjectURL(localMediaUrl);
    localMediaUrl = null;
  }
  localMediaIsVideo = false;
  if (!file) {
    previewWrap.hidden = true;
    dzBody.hidden = false;
    fileLabel.textContent = "拖拽告警媒体到此处";
    return;
  }
  fileLabel.textContent = file.name;
  previewName.textContent = file.name;
  const url = URL.createObjectURL(file);
  localMediaUrl = url;
  localMediaIsVideo = file.type.startsWith("video/") || /\.(mp4|mov|avi|mkv|webm)$/i.test(file.name);
  previewWrap.hidden = false;
  dzBody.hidden = true;
  if (localMediaIsVideo) {
    previewImg.hidden = true;
    previewImg.removeAttribute("src");
    previewVideo.hidden = false;
    previewVideo.src = url;
  } else {
    previewVideo.hidden = true;
    previewVideo.removeAttribute("src");
    previewImg.hidden = false;
    previewImg.src = url;
  }
}

fileInput.addEventListener("change", () => showLocalPreview(fileInput.files?.[0]));

["dragenter", "dragover"].forEach((ev) => {
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});
["dragleave", "drop"].forEach((ev) => {
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});
dropzone.addEventListener("drop", (e) => {
  const files = e.dataTransfer?.files;
  if (files?.length) {
    const dt = new DataTransfer();
    dt.items.add(files[0]);
    fileInput.files = dt.files;
    showLocalPreview(files[0]);
  }
});

galleryTabs.addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (!tab) return;
  setActiveLayer(tab.dataset.layer);
});

function openLightbox(url) {
  if (!url) return;
  lbImg.src = url;
  lightbox.hidden = false;
  lightbox.setAttribute("aria-hidden", "false");
}
function closeLightbox() {
  lightbox.hidden = true;
  lightbox.setAttribute("aria-hidden", "true");
  lbImg.removeAttribute("src");
}
document.getElementById("openLightbox").addEventListener("click", () => {
  const layer = currentLayers[activeLayer];
  if (!layer?.url || layer.video) return;
  openLightbox(layer.url);
});
document.getElementById("lbClose").addEventListener("click", closeLightbox);
lightbox.addEventListener("click", (e) => {
  if (e.target === lightbox) closeLightbox();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !lightbox.hidden) closeLightbox();
});

document.getElementById("clearHistory").addEventListener("click", () => {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  const fd = new FormData();
  fd.append("file", file);
  fd.append("person_nearby", document.getElementById("person").value);

  const isVideo = file.type.startsWith("video/");
  showProcess(isVideo);
  setLoading(true);
  setPipeline("running");
  outputDeck.scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const resp = await fetch("/api/analyze", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      hideProcess();
      resultEmpty.hidden = true;
      result.hidden = false;
      paintDecision("失败");
      reasonEl.textContent = data.detail || "请求失败";
      resultHint.textContent = "判别失败";
      fullVideoPanel.hidden = true;
      setPipeline("idle");
      return;
    }
    renderResult(data);
    pushHistory(data);
    setPipeline("done");
  } catch (err) {
    hideProcess();
    resultEmpty.hidden = true;
    result.hidden = false;
    paintDecision("失败");
    reasonEl.textContent = String(err);
    resultHint.textContent = "网络或服务异常";
    fullVideoPanel.hidden = true;
    setPipeline("idle");
  } finally {
    setLoading(false);
  }
});

playFullBtn.addEventListener("click", () => {
  if (fullVideo.paused) fullVideo.play().catch(() => {});
  else fullVideo.pause();
});
seekBackBtn.addEventListener("click", () => {
  fullVideo.currentTime = Math.max(0, (fullVideo.currentTime || 0) - 5);
});
seekFwdBtn.addEventListener("click", () => {
  const d = Number.isFinite(fullVideo.duration) ? fullVideo.duration : 1e9;
  fullVideo.currentTime = Math.min(d, (fullVideo.currentTime || 0) + 5);
});

batchBtn.addEventListener("click", async () => {
  batchMsg.textContent = "批量处理中，请稍候…";
  batchBtn.disabled = true;
  const fd = new FormData();
  fd.append("person_nearby", "unknown");
  try {
    const resp = await fetch("/api/batch", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      batchMsg.textContent = data.detail || "批量失败";
      return;
    }
    batchMsg.innerHTML = `完成 ${data.count} 个。Excel：<a href="${data.excel_url}" target="_blank">下载</a>`;
  } catch (err) {
    batchMsg.textContent = String(err);
  } finally {
    batchBtn.disabled = false;
  }
});

renderHistory();
