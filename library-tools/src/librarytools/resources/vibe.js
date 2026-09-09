/* A local, unranked audition workspace. Source audio is never edited here. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const token = document.querySelector('meta[name="vibe-token"]').content;
  const fields = {
    bpm: "bpm", anchor_start_s: "anchor-start", anchor_end_s: "anchor-end",
    anchor_bars: "anchor-bars", vocal_start_s: "vocal-start", vocal_end_s: "vocal-end",
    vocal_fit_beats: "vocal-fit", offset_beats: "offset-beats", repeat_beats: "repeat-beats",
    anchor_gain_db: "anchor-gain", vocal_gain_db: "vocal-gain",
  };
  const decisionLabels = { works: "Works", does_not_work: "Doesn’t work", unsure: "Unsure" };
  let session = null;
  let revision = 0;
  let pending = false;
  let rendered = null;
  let buffers = null;
  let context = null;
  let sources = [];
  let layerGains = {};
  let playing = false;
  let starting = false;
  let playbackSerial = 0;
  let animationFrame = null;
  let startedAt = 0;
  let loopDuration = 0;
  const muted = { anchor: false, vocal: false };

  function status(message, kind = "") {
    $("status").textContent = message;
    $("status").className = `notice${kind ? ` ${kind}` : ""}`;
  }

  function refreshControls() {
    $("render").disabled = !session || pending;
    $("render").textContent = pending ? "Working…" : "Render audition";
    $("play").disabled = !buffers || pending || playing || starting;
    $("stop").disabled = !playing && !starting;
    $("feedback-controls").disabled = !rendered || pending;
    $("save-feedback").disabled = !rendered || pending;
    $("save-feedback").textContent = pending ? "Working…" : "Save listening feedback";
    for (const role of ["anchor", "vocal"]) {
      const button = $(`mute-${role}`);
      button.disabled = !buffers || pending;
      button.setAttribute("aria-pressed", String(muted[role]));
      button.textContent = `${muted[role] ? "Unmute" : "Mute"} ${role === "anchor" ? "groove" : "vocal"}`;
    }
    document.querySelectorAll(".load-recipe").forEach((button) => { button.disabled = pending; });
  }

  function audioContext() {
    if (!context) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) throw new Error("This browser does not support synchronized Web Audio playback.");
      context = new AudioContextClass();
    }
    return context;
  }

  function pauseSources() {
    $("anchor-source").pause();
    $("vocal-source").pause();
  }

  function stopScene() {
    playbackSerial += 1;
    starting = false;
    playing = false;
    for (const source of sources) {
      try { source.stop(); } catch (_) { /* A stopped source needs no further action. */ }
      source.disconnect();
    }
    sources = [];
    for (const gain of Object.values(layerGains)) gain.disconnect();
    layerGains = {};
    if (animationFrame !== null) cancelAnimationFrame(animationFrame);
    animationFrame = null;
    $("playhead").hidden = true;
    $("position").textContent = rendered ? `Ready · ${rendered.duration_s.toFixed(2)} s loop` : "Not rendered";
    refreshControls();
  }

  function invalidate(message = "Recipe edited. Render the audition before listening or saving feedback.") {
    revision += 1;
    rendered = null;
    buffers = null;
    stopScene();
    $("render-info").textContent = "Edits need a fresh render.";
    status(message);
    drawWaveforms();
    drawTimeline();
  }

  function currentSource(role) {
    const list = role === "anchor" ? session.anchors : session.vocals;
    return list.find((source) => source.id === $(`${role}-select`).value);
  }

  function readSelection() {
    const recipe = { bars: 8 };
    for (const [name, id] of Object.entries(fields)) {
      const raw = $(id).value;
      recipe[name] = raw === "" ? NaN : Number(raw);
    }
    return { anchor_id: $("anchor-select").value, vocal_id: $("vocal-select").value, recipe };
  }

  function fillCandidates(role, candidates) {
    const select = $(`${role}-select`);
    select.replaceChildren();
    for (const candidate of candidates) {
      const option = document.createElement("option");
      option.value = candidate.id;
      option.textContent = `${candidate.name} · ${candidate.duration_s.toFixed(2)} s`;
      select.append(option);
    }
  }

  function syncSource(role, resetCuts = false) {
    const source = currentSource(role);
    const player = $(`${role}-source`);
    player.pause();
    player.src = `/source/${encodeURIComponent(source.id)}`;
    for (const edge of ["start", "end"]) $(`${role}-${edge}`).max = String(source.duration_s);
    if (resetCuts) {
      $(`${role}-start`).value = "0";
      $(`${role}-end`).value = String(role === "anchor" ? source.duration_s : Math.min(0.5, source.duration_s));
      if (role === "anchor") $("anchor-bars").value = String(source.suggested_bars || 1);
      else $("vocal-fit").value = "0";
    }
    $(`${role}-duration`).textContent = `${source.duration_s.toFixed(3)} s source`;
    if (role === "anchor") {
      $("anchor-hint").textContent = `Initial suggestion: ${source.suggested_bars || 1} ${(source.suggested_bars || 1) === 1 ? "bar" : "bars"}, based on duration. Check the bar count and cut by listening.`;
    }
  }

  function drawWaveform(role) {
    if (!session) return;
    const source = currentSource(role);
    if (!source) return;
    const canvas = $(`${role}-waveform`);
    const width = Math.max(1, canvas.clientWidth);
    const height = 100;
    const scale = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(scale, scale);
    ctx.clearRect(0, 0, width, height);
    const start = Number($(`${role}-start`).value);
    const end = Number($(`${role}-end`).value);
    const valid = Number.isFinite(start) && Number.isFinite(end) && end > start && start >= 0 && end <= source.duration_s;
    const left = Math.max(0, Math.min(width, start / source.duration_s * width));
    const right = Math.max(0, Math.min(width, end / source.duration_s * width));
    if (valid) {
      ctx.fillStyle = role === "anchor" ? "#263627" : "#392c23";
      ctx.fillRect(left, 0, right - left, height);
    }
    const peaks = source.waveform || [];
    const stride = width / Math.max(1, peaks.length);
    peaks.forEach((peak, i) => {
      const x = i * stride;
      const amplitude = Math.max(0.01, Math.min(1, Number(peak) || 0)) * 39;
      ctx.fillStyle = valid && x >= left && x <= right ? (role === "anchor" ? "#c1e6a0" : "#eeb990") : "#53635a";
      ctx.fillRect(x, height / 2 - amplitude, Math.max(1, stride * 0.72), amplitude * 2);
    });
    if (valid) {
      ctx.fillStyle = role === "anchor" ? "#c1e6a0" : "#eeb990";
      ctx.fillRect(left, 0, 1, height);
      ctx.fillRect(Math.min(width - 1, right), 0, 1, height);
    }
    $(`${role}-region`).textContent = valid ? `${start.toFixed(3)}–${end.toFixed(3)} s · ${(end - start).toFixed(3)} s selected` : "Choose valid start and end times";
  }

  function drawWaveforms() {
    drawWaveform("anchor");
    drawWaveform("vocal");
  }

  function drawTimeline() {
    if (!session) return;
    const recipe = readSelection().recipe;
    const events = $("vocal-events");
    events.replaceChildren();
    const bpm = recipe.bpm;
    const lengthBeats = recipe.vocal_fit_beats || ((recipe.vocal_end_s - recipe.vocal_start_s) * bpm / 60);
    const offset = recipe.offset_beats;
    const repeat = recipe.repeat_beats;
    if (![bpm, lengthBeats, offset, repeat].every(Number.isFinite) || bpm <= 0 || lengthBeats <= 0 || offset < 0 || repeat < 0) {
      $("scene-summary").textContent = "Enter valid timing and cut points to preview vocal placement.";
      return;
    }
    let count = 0;
    // A hard display bound also covers partially entered, very small repeat intervals.
    for (let beat = offset; beat + lengthBeats <= 32 + 1e-8 && count < 256; beat += repeat) {
      const event = document.createElement("span");
      event.className = "vocal-event";
      event.style.left = `${beat / 32 * 100}%`;
      event.style.width = `${lengthBeats / 32 * 100}%`;
      events.append(event);
      count += 1;
      if (repeat === 0) break;
    }
    const sceneSeconds = 32 * 60 / bpm;
    const phrase = repeat === 0 ? "once" : `every ${repeat} beats`;
    $("scene-summary").textContent = `8 bars · ${sceneSeconds.toFixed(2)} seconds · vocal after ${offset} beats, ${phrase}. ${count} complete ${count === 1 ? "cut" : "cuts"} shown. Check alignment by ear.`;
    $("scene-timeline").setAttribute("aria-label", $("scene-summary").textContent);
  }

  async function request(url, body) {
    const options = body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json", "X-Vibe-Token": token }, body: JSON.stringify(body),
    };
    const response = await fetch(url, { ...options, cache: "no-store" });
    let data;
    try { data = await response.json(); } catch (_) { throw new Error(`The local server returned an unreadable response (${response.status}).`); }
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
    return data;
  }

  async function decodeLayer(url, ctx) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      let reason = "The rendered audio could not be loaded. Render again to verify the session.";
      try { reason = (await response.json()).error || reason; } catch (_) { /* Keep the useful fallback for non-JSON audio errors. */ }
      throw new Error(reason);
    }
    return ctx.decodeAudioData(await response.arrayBuffer());
  }

  async function renderAudition(event) {
    event.preventDefault();
    if (!session || pending || !$("recipe-form").reportValidity()) return;
    invalidate("Rendering aligned groove and vocal previews…");
    pauseSources();
    const requestRevision = revision;
    const selection = readSelection();
    if (!Object.values(selection.recipe).every(Number.isFinite)) {
      status("Complete all recipe fields with finite numbers.", "error");
      return;
    }
    pending = true;
    status("Rendering aligned groove and vocal previews…", "pending");
    refreshControls();
    try {
      const ctx = audioContext();
      const result = await request("/api/render", selection);
      if (requestRevision !== revision) return;
      const [anchor, vocal] = await Promise.all([
        decodeLayer(result.audio.anchor, ctx), decodeLayer(result.audio.vocal, ctx),
      ]);
      if (requestRevision !== revision) return;
      if (anchor.length !== vocal.length || anchor.sampleRate !== vocal.sampleRate || anchor.length === 0) {
        throw new Error("The rendered layers have different lengths. Render again before auditioning.");
      }
      rendered = result;
      buffers = { anchor, vocal };
      loopDuration = anchor.length / anchor.sampleRate;
      for (const [name, id] of Object.entries(fields)) {
        if (result.selection?.recipe?.[name] !== undefined) setFieldValue(id, result.selection.recipe[name]);
      }
      $("position").textContent = `Ready · ${loopDuration.toFixed(2)} s loop`;
      $("render-info").textContent = `${result.cache_hit ? "Verified cached render" : "Fresh render"} · ${result.render_id.slice(0, 10)}`;
      status("Audition ready. Play the scene, compare layers, then record what you hear.");
      drawWaveforms();
      drawTimeline();
    } catch (error) {
      if (requestRevision === revision) status(error.message || "The audition could not be rendered.", "error");
    } finally {
      pending = false;
      refreshControls();
    }
  }

  function animatePlayhead() {
    if (!playing) return;
    const elapsed = Math.max(0, context.currentTime - startedAt);
    const position = elapsed % loopDuration;
    $("playhead").hidden = false;
    $("playhead").style.left = `${position / loopDuration * 100}%`;
    $("position").textContent = `Bar ${Math.min(8, Math.floor(position / loopDuration * 8) + 1)} / 8 · ${position.toFixed(1)} s`;
    animationFrame = requestAnimationFrame(animatePlayhead);
  }

  async function playScene() {
    if (!buffers || pending || playing || starting) return;
    pauseSources();
    const requestRevision = revision;
    const requestPlayback = ++playbackSerial;
    starting = true;
    refreshControls();
    try {
      const ctx = audioContext();
      await ctx.resume();
      if (requestRevision !== revision || requestPlayback !== playbackSerial || !buffers) return;
      startedAt = ctx.currentTime + 0.05;
      for (const role of ["anchor", "vocal"]) {
        const source = ctx.createBufferSource();
        source.buffer = buffers[role];
        source.loop = true;
        source.loopStart = 0;
        source.loopEnd = loopDuration;
        const gain = ctx.createGain();
        gain.gain.value = muted[role] ? 0 : 1;
        source.connect(gain);
        gain.connect(ctx.destination);
        layerGains[role] = gain;
        sources.push(source);
      }
      // Both complete scene buffers use one clock, one start and one loop interval.
      for (const source of sources) source.start(startedAt);
      playing = true;
      starting = false;
      animatePlayhead();
      status("Playing the rendered scene. Mute the groove to hear the vocal alone, or mute the vocal to hear the groove.");
    } catch (error) {
      if (requestPlayback === playbackSerial) {
        stopScene();
        status(error.message || "Playback could not start. Try Play scene again.", "error");
      }
    } finally {
      if (requestPlayback === playbackSerial) starting = false;
      refreshControls();
    }
  }

  function toggleMute(role) {
    muted[role] = !muted[role];
    if (layerGains[role]) {
      const gain = layerGains[role].gain;
      gain.cancelScheduledValues(context.currentTime);
      gain.setTargetAtTime(muted[role] ? 0 : 1, context.currentTime, 0.008);
    }
    refreshControls();
  }

  function setFieldValue(id, value) {
    const input = $(id);
    // Persisted recipes may use a beat length beyond the menu's convenient presets.
    if (input.tagName === "SELECT" && !Array.from(input.options).some((option) => option.value === String(value))) {
      const option = document.createElement("option");
      option.value = String(value);
      option.textContent = `Fit to ${value} beats`;
      input.append(option);
    }
    input.value = String(value);
  }

  function loadRecipe(entry) {
    if (pending) return;
    const selection = entry.selection;
    if (!selection || !session.anchors.some((source) => source.id === selection.anchor_id) || !session.vocals.some((source) => source.id === selection.vocal_id)) {
      status("This saved recipe refers to a source that is unavailable in this session.", "error");
      return;
    }
    pauseSources();
    $("anchor-select").value = selection.anchor_id;
    $("vocal-select").value = selection.vocal_id;
    syncSource("anchor");
    syncSource("vocal");
    for (const [name, id] of Object.entries(fields)) setFieldValue(id, selection.recipe[name]);
    $("feedback-note").value = entry.note || "";
    document.querySelectorAll('input[name="decision"]').forEach((input) => { input.checked = input.value === entry.decision; });
    invalidate("Saved recipe loaded. Render it to verify the audio before listening or saving new feedback.");
  }

  function drawHistory() {
    const feedback = session.feedback || [];
    $("history-list").replaceChildren();
    $("history-count").textContent = `${feedback.length} saved`;
    $("history-empty").hidden = feedback.length > 0;
    for (const entry of [...feedback].reverse()) {
      const item = document.createElement("li");
      item.className = "history-item";
      const text = document.createElement("div");
      const title = document.createElement("p");
      title.className = "history-title";
      const anchor = session.anchors.find((source) => source.id === entry.selection?.anchor_id);
      const vocal = session.vocals.find((source) => source.id === entry.selection?.vocal_id);
      title.textContent = `${anchor?.name || "Unavailable groove"} + ${vocal?.name || "Unavailable vocal"}`;
      const detail = document.createElement("p");
      detail.className = "history-detail";
      detail.textContent = `${decisionLabels[entry.decision] || "Unknown decision"} · ${entry.selection?.recipe?.bpm ?? "—"} BPM · ${entry.render_id.slice(0, 10)}`;
      text.append(title, detail);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary small load-recipe";
      button.textContent = "Load recipe";
      button.addEventListener("click", () => loadRecipe(entry));
      item.append(text, button);
      if (entry.note) {
        const note = document.createElement("p");
        note.className = "history-note";
        note.textContent = entry.note;
        item.append(note);
      }
      $("history-list").append(item);
    }
    refreshControls();
  }

  async function saveFeedback(event) {
    event.preventDefault();
    if (!rendered || pending || !$("feedback-form").reportValidity()) return;
    const decision = document.querySelector('input[name="decision"]:checked');
    if (!decision) return;
    const requestRevision = revision;
    const renderId = rendered.render_id;
    pending = true;
    status("Saving your listening feedback…", "pending");
    refreshControls();
    try {
      const result = await request("/api/feedback", { render_id: renderId, decision: decision.value, note: $("feedback-note").value });
      session.feedback = result.feedback;
      drawHistory();
      if (requestRevision === revision) status("Listening feedback saved with this exact rendered recipe.");
    } catch (error) {
      if (requestRevision === revision) status(error.message || "Feedback could not be saved.", "error");
    } finally {
      pending = false;
      refreshControls();
    }
  }

  async function loadSession() {
    $("retry-load").hidden = true;
    status("Loading the session…");
    try {
      const result = await request("/api/state");
      if (!result.anchors?.length || !result.vocals?.length) throw new Error("This session needs at least one groove and one vocal candidate.");
      session = result;
      fillCandidates("anchor", session.anchors);
      fillCandidates("vocal", session.vocals);
      $("bpm").value = String(session.bpm);
      syncSource("anchor", true);
      syncSource("vocal", true);
      $("recipe-controls").disabled = false;
      invalidate("Choose a groove and a vocal cut, then render an audition. Candidate suitability still needs listening.");
      drawHistory();
    } catch (error) {
      status(error.message || "The local audition session could not be loaded.", "error");
      $("retry-load").hidden = false;
    }
  }

  $("recipe-form").addEventListener("submit", renderAudition);
  $("feedback-form").addEventListener("submit", saveFeedback);
  $("play").addEventListener("click", playScene);
  $("stop").addEventListener("click", () => { stopScene(); pauseSources(); });
  $("retry-load").addEventListener("click", loadSession);
  for (const [_, id] of Object.entries(fields)) {
    $(id).addEventListener("input", () => invalidate());
  }
  for (const role of ["anchor", "vocal"]) {
    $(`${role}-select`).addEventListener("change", () => {
      syncSource(role, true);
      invalidate("Candidate changed. Check the region and timing, then render a new audition.");
    });
    $(`mute-${role}`).addEventListener("click", () => toggleMute(role));
    $(`${role}-source`).addEventListener("play", () => {
      stopScene();
      $(`${role === "anchor" ? "vocal" : "anchor"}-source`).pause();
    });
    for (const edge of ["start", "end"]) {
      $(`${role}-mark-${edge}`).addEventListener("click", () => {
        const source = currentSource(role);
        $(`${role}-${edge}`).value = String(Math.min(source.duration_s, Math.max(0, $(`${role}-source`).currentTime)));
        invalidate();
      });
    }
  }
  window.addEventListener("resize", drawWaveforms);
  window.addEventListener("pagehide", () => { stopScene(); pauseSources(); });
  loadSession();
})();
