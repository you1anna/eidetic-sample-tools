'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const player = $('player');
  const token = document.querySelector('meta[name="vibe-token"]').content;
  let sources = [], decisions = {}, current = null, view = 'all';
  let busy = false, lastChoice = null, mediaGeneration = 0, mediaFailed = false;
  let mode = 'browser', batchIndex = 0, batchCount = 1, counts = null;
  let liveState = null, livePreview = null, liveDisconnected = false, uiGeneration = 0;
  let handoff = {available: false, reason: 'Checking the library index…'};

  const clock = value => {
    const seconds = Math.max(0, Number.isFinite(value) ? value : 0);
    const whole = Math.floor(seconds);
    const tenths = Math.floor((seconds - whole) * 10);
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}.${tenths}`;
  };
  const role = item => item.kind.replace(' candidate', '');
  let played = '', unplayed = '';
  function waveColours() {
    const styles = getComputedStyle(document.documentElement);
    played = styles.getPropertyValue('--ink').trim();
    unplayed = styles.getPropertyValue('--line-strong').trim();
  }
  function drawWave() {
    const canvas = $('wave');
    const width = Math.max(1, canvas.clientWidth), height = 96;
    const scale = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(width * scale)) {
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const peaks = current?.waveform || [];
    if (!peaks.length) return;
    if (!played) waveColours();
    const progress = current.duration_s ? Math.min(1, player.currentTime / current.duration_s) : 0;
    // Aggregate the stored peaks into legible bars rather than one hairline each.
    const step = 4, bars = Math.max(1, Math.floor(width / step));
    const loudest = Math.max(...peaks) || 1;
    const split = progress * width;
    // A continuous baseline keeps quiet passages a line rather than dots.
    ctx.fillStyle = unplayed;
    ctx.fillRect(0, height / 2 - .5, width, 1);
    ctx.fillStyle = played;
    ctx.fillRect(0, height / 2 - .5, split, 1);
    for (let index = 0; index < bars; index += 1) {
      const from = Math.floor(index * peaks.length / bars);
      const to = Math.max(from + 1, Math.floor((index + 1) * peaks.length / bars));
      const peak = Math.max(...peaks.slice(from, to));
      const bar = Math.max(1, (peak / loudest) * (height - 12));
      const x = index * step;
      ctx.fillStyle = (x + step / 2) / width <= progress ? played : unplayed;
      ctx.fillRect(x, (height - bar) / 2, step - 1, bar);
    }
  }
  function status(message, error = false) {
    $('status').textContent = message;
    $('status').classList.toggle('error', error);
  }
  async function request(url, body) {
    const response = await fetch(url, body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Vibe-Token': token},
      body: JSON.stringify(body)
    });
    const result = response.headers.get('content-type')?.includes('application/json')
      ? await response.json() : {error: response.status === 403
        ? 'This session changed. Reload the page before saving again.'
        : `The local server returned an unexpected response (${response.status}). Reload and retry.`};
    if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
    return result;
  }
  const filtered = () => sources.filter(item => view === 'all' || decisions[item.id] === 'keep');
  function playbackState() {
    const playing = mode === 'live' ? Boolean(liveState?.loaded?.candidate?.is_playing) : !player.paused;
    $('play-glyph').textContent = playing ? '❙❙' : '▶';
    $('play').setAttribute('aria-label', playing ? 'Pause' : mediaFailed ? 'Retry play' : 'Play');
    $('time').textContent = `${clock(player.currentTime)} / ${clock(current?.duration_s || 0)}`;
    $('seek').value = Number.isFinite(player.currentTime) ? player.currentTime : 0;
    $('seek').disabled = mode === 'live' || !current || player.readyState < 1;
    drawWave();
  }
  function controls() {
    $('play').disabled = busy || !current || Boolean(current.error) || (mode === 'live' && (liveDisconnected || liveState?.loaded?.candidate?.sample_id !== current.id));
    $('batch-prev').disabled = busy || batchIndex === 0;
    $('batch-next').disabled = busy || batchIndex + 1 >= batchCount;
    for (const id of ['attach-preview', 'load-candidate', 'load-reference', 'live-confirm', 'live-stop']) $(id).disabled = busy;
    $('load-candidate').disabled = $('load-reference').disabled = busy || !current || Boolean(current.error) || !liveState?.attached || liveDisconnected;
    $('gain').disabled = busy || (mode === 'live' && (!liveState?.loaded?.candidate || liveDisconnected));
    $('loop').disabled = busy || (mode === 'live' && (!liveState?.loaded?.candidate || liveDisconnected));
    $('playback-mode').disabled = busy;
    $('warp').disabled = $('warp-mode').disabled = busy || mode !== 'live' || !liveState?.loaded?.candidate || liveDisconnected;
    $('keep').disabled = busy || !current || (view === 'kept' && decisions[current.id] === 'keep');
    $('skip').disabled = busy || !current;
    $('keep-label').textContent = view === 'kept' ? 'Kept' : 'Keep & next';
    $('skip-label').textContent = view === 'kept' ? 'Skip' : 'Skip & next';
    $('undo').hidden = !lastChoice;
    $('undo').disabled = busy;
    $('all').disabled = $('kept').disabled = busy;
    $('prepare').disabled = busy || !handoff.available;
    document.querySelectorAll('#samples button').forEach(button => { button.disabled = busy; });
  }
  function paint() {
    const keptCount = counts?.keep ?? sources.filter(item => decisions[item.id] === 'keep').length;
    const reviewed = counts ? counts.total - counts.unreviewed : sources.filter(item => decisions[item.id] !== 'unreviewed').length;
    $('all').textContent = `All samples (${sources.length})`;
    const batchKept = sources.filter(item => decisions[item.id] === 'keep').length;
    $('kept').textContent = batchCount > 1 ? `Kept in batch (${batchKept}; ${keptCount} total)` : `Kept (${keptCount})`;
    $('empty').textContent = batchCount > 1 && keptCount ? 'No kept samples in this batch. Browse other batches to compare your saved shortlist.' : 'No samples kept yet. Play a sample and choose Keep.';
    $('all').setAttribute('aria-pressed', String(view === 'all'));
    $('kept').setAttribute('aria-pressed', String(view === 'kept'));
    $('progress').textContent = `${reviewed} / ${counts?.total ?? sources.length} reviewed`;
    $('batches').hidden = batchCount === 1;
    $('batch-label').textContent = `${batchIndex + 1} / ${batchCount}`;
    $('empty').hidden = filtered().length !== 0;
    $('handoff').hidden = view !== 'kept' || keptCount === 0;
    $('handoff-status').textContent = handoff.available
      ? 'Creates a review sheet for these originals. No audio is promoted or exported.'
      : `Shortlist saved. ${handoff.reason}`;
    $('samples').replaceChildren();
    for (const item of filtered()) {
      const row = document.createElement('li');
      const button = document.createElement('button');
      button.className = 'source';
      button.dataset.decision = decisions[item.id];
      button.setAttribute('aria-current', String(item.id === current?.id));
      button.setAttribute('aria-label', `Audition ${item.name}`);
      const order = document.createElement('span');
      order.className = 'order'; order.textContent = String(sources.indexOf(item) + 1).padStart(2, '0');
      const name = document.createElement('span');
      name.className = 'name';
      const title = document.createElement('span');
      title.className = 'title'; title.textContent = item.name;
      const detail = document.createElement('span');
      detail.className = 'detail';
      for (const text of [role(item), clock(item.duration_s), item.history_status?.replaceAll('_', ' '), item.error ? 'Audio unavailable' : ''].filter(Boolean)) {
        const part = document.createElement('span');
        part.textContent = text;
        detail.append(part);
      }
      name.append(title, detail);
      const badge = document.createElement('span');
      badge.className = 'badge';
      // The Kept view puts a Remove control in this column instead of a state word.
      badge.textContent = view === 'kept' ? '' : {keep: 'Kept', skip: 'Skipped', unreviewed: ''}[decisions[item.id]];
      button.append(order, name, badge);
      button.addEventListener('click', () => {
        status(`Selected: ${item.name}`);
        if (!busy) void select(item, true);
      });
      row.append(button);
      if (view === 'kept') {
        const remove = document.createElement('button');
        remove.className = 'remove quiet'; remove.textContent = 'Remove';
        remove.setAttribute('aria-label', `Remove ${item.name} from shortlist`);
        remove.addEventListener('click', () => choose(item, 'unreviewed', false));
        row.append(remove);
      }
      $('samples').append(row);
    }
    controls();
  }
  async function select(item, play = false) {
    const generation = ++uiGeneration;
    const wasBusy = busy; busy = true; controls();
    if (mode === 'live' && liveState?.attached && current?.id !== item?.id) {
      try { liveState = await request('/api/live/control', {action: 'stop'}); }
      catch (error) { liveFailure(error); busy = wasBusy; controls(); return; }
    }
    if (generation !== uiGeneration) return;
    livePreview = null; $('live-preview').hidden = $('live-confirm').hidden = true;
    mediaGeneration += 1;
    player.pause();
    current = item || null;
    mediaFailed = false;
    if (current) {
      if (mode === 'browser' && !current.error) player.src = `/source/${current.id}`;
      else player.removeAttribute('src');
      $('sample-name').textContent = current.name;
      $('sample-meta').textContent = `${role(current)} · ${clock(current.duration_s)}${current.error ? ' · ' + current.error : ''}`;
      if (current.timing_status) $('live-timing').textContent = current.timing_status;
      $('seek').max = current.duration_s;
    } else {
      player.removeAttribute('src');
      $('sample-name').textContent = batchCount > 1 && counts?.keep ? 'No kept samples in this batch' : 'Your shortlist is empty';
      $('sample-meta').textContent = 'Choose from All samples';
    }
    player.load();
    playbackState();
    paint();
    busy = wasBusy; controls();
    if (play && current && mode === 'browser') void startPlayback();
  }
  async function startPlayback() {
    if (!current || current.error) return;
    if (mode === 'live') {
      if (busy) return;
      await liveControl({action: 'play', with_reference: $('with-reference').checked});
      return;
    }
    const generation = mediaGeneration;
    const retrying = mediaFailed;
    if (retrying) { mediaFailed = false; player.load(); }
    try {
      await player.play();
      if (generation === mediaGeneration && mode === 'browser') {
        playbackState();
        if (retrying) status(`Playing: ${current.name}`);
      }
    } catch (error) {
      if (generation !== mediaGeneration || error.name === 'AbortError') return;
      status('Could not play this sample. Check the source drive is connected, then try Play again.', true);
      playbackState();
    }
  }
  async function choose(item, decision, advance = true) {
    if (busy || !item) return;
    const previous = decisions[item.id];
    busy = true; controls();
    try {
      const result = await request('/api/shortlist', {source_id: item.id, decision});
      decisions = result.decisions; counts = result.counts;
      lastChoice = {item, previous};
      $('packet-result').hidden = true;
      const suffix = decision === 'keep' ? 'Kept' : decision === 'skip' ? 'Skipped' : 'Removed from shortlist';
      status(`${suffix}: ${item.name}`);
      if (advance && view === 'all') {
        const index = sources.findIndex(source => source.id === item.id);
        const following = [...sources.slice(index + 1), ...sources.slice(0, index)]
          .find(source => decisions[source.id] === 'unreviewed');
        if (following) await select(following, !player.paused);
        else if (batchIndex + 1 < batchCount) {
          await changeBatch(batchIndex + 1, true);
        } else {
          player.pause();
          view = 'kept';
          await select(filtered()[0]);
          status(counts.unreviewed ? 'This batch is reviewed. Use Previous batch to find remaining samples.' : 'All samples reviewed. Browse batches to compare kept samples.');
        }
      } else if (view === 'kept' && !filtered().some(source => source.id === current?.id)) {
        await select(filtered()[0]);
      }
    } catch (error) {
      status(`Choice was not saved: ${error.message}`, true);
    } finally { busy = false; paint(); }
  }
  async function undo() {
    if (busy || !lastChoice) return;
    busy = true; controls();
    const saved = lastChoice;
    try {
      const result = await request('/api/shortlist', {source_id: saved.item.id, decision: saved.previous});
      decisions = result.decisions; counts = result.counts;
      lastChoice = null;
      $('packet-result').hidden = true;
      view = 'all'; await select(saved.item);
      status(`Undid the last choice for ${saved.item.name}`);
    } catch (error) { status(`Undo was not saved: ${error.message}`, true); }
    finally { busy = false; paint(); }
  }
  function setView(next) {
    if (busy) return;
    view = next;
    if (!filtered().some(item => item.id === current?.id)) select(filtered()[0]);
    else paint();
  }
  $('play').addEventListener('click', () => {
    if (mode === 'live') { if (liveState?.loaded?.candidate?.is_playing) void liveControl({action: 'stop'}); else void startPlayback(); }
    else if (player.paused) void startPlayback(); else player.pause();
  });
  $('seek').addEventListener('input', () => {
    if (player.readyState >= 1) player.currentTime = Number($('seek').value);
    playbackState();
  });
  $('loop').addEventListener('click', () => {
    const next = $('loop').getAttribute('aria-pressed') !== 'true';
    if (mode === 'live') { void liveControl({action: 'loop', loop: next, with_reference: $('with-reference').checked}); }
    else { $('loop').setAttribute('aria-pressed', String(next)); player.loop = next; }
  });
  $('info-toggle').addEventListener('click', () => {
    const opening = $('info').hidden;
    $('info').hidden = !opening;
    $('info-toggle').setAttribute('aria-expanded', String(opening));
  });
  window.addEventListener('resize', drawWave);
  for (const name of ['timeupdate', 'loadedmetadata', 'play', 'pause', 'ended', 'emptied'])
    player.addEventListener(name, playbackState);
  player.addEventListener('error', () => {
    if (!current || !player.getAttribute('src')) return;
    mediaFailed = true; playbackState();
    status('Audio unavailable. Check the source drive and retry Play. Changed source files need a new session.', true);
  });
  $('keep').addEventListener('click', () => choose(current, 'keep'));
  $('skip').addEventListener('click', () => choose(current, 'skip'));
  $('undo').addEventListener('click', undo);
  $('all').addEventListener('click', () => setView('all'));
  $('kept').addEventListener('click', () => setView('kept'));
  $('playlist').addEventListener('click', async event => {
    event.preventDefault();
    try {
      const response = await fetch('/api/shortlist/playlist');
      if (!response.ok) throw new Error((await response.json()).error || 'Playlist unavailable');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = 'eidetic-shortlist.m3u8'; document.body.append(link);
      link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      status('Playlist downloaded. It points to your kept original files on this Mac.');
    } catch (error) { status(error.message, true); }
  });
  $('prepare').addEventListener('click', async () => {
    if (busy) return;
    busy = true; controls();
    try {
      const result = await request('/api/shortlist/packet', {});
      $('packet-result').hidden = false;
      $('packet-message').textContent = result.message;
      $('packet-command').textContent = result.next_step;
      status(`Curation sheet prepared for ${result.count} kept samples. No audio was exported.`);
    } catch (error) { status(`Curation sheet was not created: ${error.message}`, true); }
    finally { busy = false; controls(); }
  });
  document.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.repeat || busy) return;
    if (event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
    if (event.key === ' ' && event.target.closest('button, a')) return;
    const key = event.key.toLowerCase();
    if (key === ' ') { event.preventDefault(); $('play').click(); }
    else if (key === 'k') { event.preventDefault(); $('keep').click(); }
    else if (key === 's') { event.preventDefault(); $('skip').click(); }
    else if (key === 'arrowright' || key === 'arrowleft') {
      const items = filtered(), index = items.findIndex(item => item.id === current?.id);
      const next = items[index + (key === 'arrowright' ? 1 : -1)];
      if (next) {
        event.preventDefault();
        status(`Selected: ${next.name}`);
        select(next, !player.paused);
      }
    }
  });
  function liveFailure(error) {
    liveDisconnected = true;
    player.pause(); player.removeAttribute('src'); player.load();
    $('live-status').textContent = error.message;
    status(`Live unavailable or action refused: ${error.message}`, true);
    controls();
  }
  function paintLive() {
    liveDisconnected = false;
    const identity = liveState.identity;
    $('live-status').textContent = `${liveState.attached ? 'Attached' : 'Connected; attachment required'}: ${identity.set_name || identity.set_path || 'Unsaved Set'} · ${liveState.tempo} BPM`;
    if (!$('saved-set').value) $('saved-set').value = identity.set_path || '';
    const clip = liveState.loaded?.candidate;
    if (clip) {
      $('warp').checked = Boolean(clip.warping);
      const available = Array.isArray(clip.available_warp_modes) ? clip.available_warp_modes : [clip.available_warp_modes];
      $('warp-mode').replaceChildren();
      const labels = ['Beats', 'Tones', 'Texture', 'Re-Pitch', 'Complex', 'REX', 'Complex Pro'];
      for (const number of available) { const option = document.createElement('option'); option.value = number; option.textContent = labels[number] || `Mode ${number}`; $('warp-mode').append(option); }
      $('warp-mode').value = clip.warp_mode;
      $('gain').value = clip.gain;
      $('gain-label').textContent = `Live clip ${clip.gain_display_string}`;
      $('loop').setAttribute('aria-pressed', String(Boolean(clip.looping)));
      $('live-timing').textContent = `Grid unverified · Warp ${clip.warping ? 'on' : 'off'} · mode ${clip.warp_mode} · loop ${clip.loop_start}–${clip.loop_end} ${clip.warping ? 'beats' : 'seconds'}. Correct grid and boundaries manually in Live. Set tempo stays ${liveState.tempo} BPM.`;
    }
    playbackState(); controls();
  }
  async function liveControl(body) {
    if (busy) return;
    busy = true; controls();
    try { liveState = await request('/api/live/control', body); paintLive(); }
    catch (error) { liveFailure(error); }
    finally { busy = false; controls(); }
  }
  async function previewLive(url, body) {
    if (busy) return;
    busy = true; controls();
    try {
      livePreview = await request(url, body);
      $('live-preview').textContent = JSON.stringify(livePreview, null, 2);
      $('live-preview').hidden = $('live-confirm').hidden = false;
      status('Review this exact change, then confirm to apply it in Live.');
    } catch (error) { liveFailure(error); }
    finally { busy = false; controls(); }
  }
  async function changeBatch(index, internal = false) {
    if (busy && !internal) return;
    const priorBusy = busy; busy = true; controls();
    player.pause();
    try {
      if (mode === 'live' && liveState?.attached) liveState = await request('/api/live/control', {action: 'stop'});
      const state = await request('/api/batch', {batch_index: index});
      sources = state.sources; batchIndex = state.batch_index; batchCount = state.batch_count;
      view = 'all';
      await select(sources.find(item => decisions[item.id] === 'unreviewed') || sources[0]);
      status(`Batch ${batchIndex + 1} of ${batchCount}. Choices remain saved across every batch.`);
    } catch (error) { status(error.message, true); }
    finally { busy = priorBusy; paint(); }
  }
  $('batch-prev').addEventListener('click', () => changeBatch(batchIndex - 1));
  $('batch-next').addEventListener('click', () => changeBatch(batchIndex + 1));
  $('playback-mode').addEventListener('change', async () => {
    ++uiGeneration;
    const next = $('playback-mode').value;
    player.pause(); player.removeAttribute('src'); player.load();
    busy = true; controls();
    try {
      if (mode === 'live' && liveState?.attached) liveState = await request('/api/live/control', {action: 'stop'});
      mode = next;
      $('live-panel').hidden = mode !== 'live';
      if (mode === 'live') {
        liveState = await request('/api/live/status'); paintLive();
      } else {
        livePreview = null; $('live-confirm').hidden = $('live-preview').hidden = true;
        $('gain').value = player.volume; $('gain-label').textContent = `Browser ${Math.round(player.volume * 100)}%`;
        $('loop').setAttribute('aria-pressed', String(player.loop));
        await select(current);
        status('Browser playback selected. Press Play to listen.');
      }
    } catch (error) { mode = 'live'; $('playback-mode').value = 'live'; $('live-panel').hidden = false; liveFailure(error); }
    finally { busy = false; controls(); }
  });
  $('attach-preview').addEventListener('click', () => previewLive('/api/live/attach-preview', {saved_set: $('saved-set').value}));
  for (const role of ['candidate', 'reference']) $('load-' + role).addEventListener('click', () => {
    if (current) void previewLive('/api/live/load-preview', {source_id: current.id, role});
  });
  $('live-confirm').addEventListener('click', async () => {
    if (busy || !livePreview) return;
    busy = true; controls();
    const preview = livePreview; livePreview = null;
    $('live-confirm').hidden = true;
    try {
      liveState = await request('/api/live/confirm', {preview_id: preview.preview_id});
      $('live-preview').hidden = true; paintLive();
      status('Change read back in Live. Check the audio and save the Set manually.');
    } catch (error) { liveFailure(error); }
    finally { busy = false; controls(); }
  });
  $('live-stop').addEventListener('click', () => liveControl({action: 'stop'}));
  $('gain').addEventListener('change', () => {
    const gain = Number($('gain').value);
    if (mode === 'live') void liveControl({action: 'gain', gain, with_reference: false});
    else { player.volume = gain; $('gain-label').textContent = `Browser ${Math.round(gain * 100)}%`; }
  });
  $('warp').addEventListener('change', () => liveControl({action: 'warp', warping: $('warp').checked}));
  $('warp-mode').addEventListener('change', () => liveControl({action: 'warp_mode', warp_mode: Number($('warp-mode').value)}));
  $('live-reconcile').addEventListener('click', async () => {
    if (busy) return; busy = true; controls();
    try { const report = await request('/api/live/reconcile'); $('live-preview').textContent = JSON.stringify(report, null, 2); $('live-preview').hidden = false; status(report.next_step); }
    catch (error) { liveFailure(error); }
    finally { busy = false; controls(); }
  });
  window.setInterval(async () => {
    if (mode !== 'live' || busy) return;
    const generation = uiGeneration;
    busy = true; controls();
    try { const next = await request('/api/live/status'); if (mode === 'live' && generation === uiGeneration) { liveState = next; paintLive(); } }
    catch (error) { if (mode === 'live' && generation === uiGeneration) liveFailure(error); }
    finally { busy = false; controls(); }
  }, 5000);
  Promise.all([request('/api/sources'), request('/api/shortlist'), request('/api/shortlist/status')])
    .then(([state, saved, availability]) => {
      sources = state.sources; batchIndex = state.batch_index || 0; batchCount = state.batch_count || 1;
      decisions = saved.decisions; counts = saved.counts; handoff = availability;
      select(sources.find(item => decisions[item.id] === 'unreviewed') || sources[0]);
      status('Play a sample, then Keep or Skip. Each choice saves automatically.');
    }).catch(error => { $('sample-name').textContent = 'Session unavailable'; status(error.message, true); });
})();
