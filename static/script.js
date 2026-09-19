const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const preview = document.getElementById('preview');
const previewImg = document.getElementById('previewImg');
const previewName = document.getElementById('previewName');
const analyzeBtn = document.getElementById('analyzeBtn');
const resetBtn = document.getElementById('resetBtn');
const statusBox = document.getElementById('status');
const errorBox = document.getElementById('error');
const report = document.getElementById('report');

let selectedFile = null;

function showOnly(el) {
  [statusBox, errorBox, report].forEach(e => e.hidden = true);
  if (el) el.hidden = false;
}

function selectFile(file) {
  if (!file) return;
  selectedFile = file;
  previewImg.src = URL.createObjectURL(file);
  previewName.textContent = `${file.name} · ${(file.size / 1024).toFixed(0)} KB`;
  dropzone.hidden = true;
  preview.hidden = false;
  showOnly(null);
}

dropzone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', e => selectFile(e.target.files[0]));

['dragenter', 'dragover'].forEach(evt =>
  dropzone.addEventListener(evt, e => {
    e.preventDefault();
    dropzone.classList.add('is-dragover');
  })
);
['dragleave', 'drop'].forEach(evt =>
  dropzone.addEventListener(evt, e => {
    e.preventDefault();
    dropzone.classList.remove('is-dragover');
  })
);
dropzone.addEventListener('drop', e => {
  const file = e.dataTransfer.files[0];
  if (file) selectFile(file);
});

resetBtn.addEventListener('click', () => {
  selectedFile = null;
  fileInput.value = '';
  preview.hidden = true;
  dropzone.hidden = false;
  showOnly(null);
});

analyzeBtn.addEventListener('click', async () => {
  if (!selectedFile) return;
  showOnly(statusBox);

  const formData = new FormData();
  formData.append('file', selectedFile);

  try {
    const res = await fetch('/api/analyze', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'ما نقدر نحلل لك ');
    renderReport(data);
    showOnly(report);
  } catch (err) {
    errorBox.textContent = err.message || 'صار في خطا وقت التحليل';
    showOnly(errorBox);
  }
});

function randomRef(prefix) {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789';
  let s = '';
  for (let i = 0; i < 6; i++) s += chars[Math.floor(Math.random() * chars.length)];
  return `${prefix}-${s}`;
}

function kvRow(k, v) {
  const tr = document.createElement('tr');
  const tdK = document.createElement('td');
  const tdV = document.createElement('td');
  tdK.textContent = k;
  tdV.textContent = typeof v === 'object' ? JSON.stringify(v) : String(v);
  tdV.dir = 'ltr';
  tr.append(tdK, tdV);
  return tr;
}

function highlightCard(label, value, { muted = false, sub = null } = {}) {
  const card = document.createElement('div');
  card.className = 'highlight-card';

  const labelEl = document.createElement('div');
  labelEl.className = 'highlight-card__label';
  labelEl.textContent = label;

  const valueEl = document.createElement('div');
  valueEl.className = 'highlight-card__value' + (muted ? ' highlight-card__value--muted' : '');
  valueEl.textContent = value;

  card.append(labelEl, valueEl);

  if (sub) {
    const subEl = document.createElement('div');
    subEl.className = 'highlight-card__sub';
    subEl.dir = 'ltr';
    subEl.appendChild(sub);
    card.appendChild(subEl);
  }
  return card;
}

function renderHighlights(h) {
  const box = document.getElementById('highlightsBox');
  box.innerHTML = '';

  // الموقع
  if (h.location) {
    const link = document.createElement('a');
    link.href = h.location.maps_url;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = `${h.location.lat}, ${h.location.lon}`;
    box.appendChild(highlightCard('مكان التصوير', 'عرض على الخريطة ↗', { sub: link }));
  } else {
    box.appendChild(highlightCard('مكان التصوير', 'مافيه بيانات للموقع', { muted: true }));
  }

  // تاريخ التصوير
  box.appendChild(
    h.captured_at
      ? highlightCard('تاريخ التصوير', h.captured_at)
      : highlightCard('تاريخ التصوير', 'ماله موقع', { muted: true })
  );

  // الجهاز
  box.appendChild(
    h.device
      ? highlightCard('جهاز التصوير', h.device)
      : highlightCard('جهاز التصوير', 'ماله جهاز تصوير', { muted: true })
  );

  // الجودة
  const q = h.quality || {};
  const dimsText = q.dimensions ? `${q.dimensions.width} × ${q.dimensions.height}` : null;
  const parts = [];
  if (dimsText) parts.push(dimsText + ' px');
  if (q.megapixels) parts.push(`${q.megapixels}MP`);
  if (parts.length) {
    const sub = document.createTextNode(
      [q.file_size, q.estimated_jpeg_quality ? `جودة JPEG ~${q.estimated_jpeg_quality}%` : null]
        .filter(Boolean).join(' · ')
    );
    box.appendChild(highlightCard('دقة وجودة الصورة', parts.join(' · '), { sub }));
  } else {
    box.appendChild(highlightCard('دقة وجودة الصورة', 'غير متوفر', { muted: true }));
  }
}

function renderReport(data) {
  document.getElementById('exhibitId').textContent = randomRef('EXH');
  document.getElementById('analyzedAt').textContent = new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  document.getElementById('reportFileName').textContent = data.file_name;

  renderHighlights(data.highlights || {});

  const hashTable = document.getElementById('hashTable');
  hashTable.innerHTML = '';
  Object.entries(data.hashes).forEach(([k, v]) => hashTable.appendChild(kvRow(k.toUpperCase(), v)));

  const fp = data.fingerprint;
  const box = document.getElementById('fingerprintBox');
  box.innerHTML = '';
  const fingerprintDiv = document.createElement('div');
  fingerprintDiv.className = 'fingerprint';

  const rows = [
    ['الصيغة', fp.format || '—'],
    ['الأبعاد', fp.dimensions ? `${fp.dimensions.width} × ${fp.dimensions.height}px` : '—'],
    ['نوع ضغط الألوان (Chroma subsampling)', fp.subsampling || '—'],
    ['جودة JPEG ', fp.estimated_jpeg_quality ? `~${fp.estimated_jpeg_quality}%` : 'غير متاح'],
  ];
  rows.forEach(([k, v]) => {
    const row = document.createElement('div');
    row.className = 'fingerprint__row';
    row.innerHTML = `<span>${k}</span><span dir="ltr">${v}</span>`;
    fingerprintDiv.appendChild(row);
  });

  const guessWrap = document.createElement('div');
  guessWrap.className = 'guess';
  if (fp.guesses && fp.guesses.length) {
    const heading = document.createElement('div');
    heading.className = 'report__field-label';
    heading.style.marginBottom = '8px';
    heading.textContent = 'التطبيقات اللي ممكن مرت عليه الصورة';
    guessWrap.appendChild(heading);

    fp.guesses.forEach(g => {
      const item = document.createElement('div');
      item.className = 'guess__item';
      item.innerHTML = `<span class="guess__name">${g.name}</span><span class="guess__confidence">ثقة ${g.confidence}</span>`;
      guessWrap.appendChild(item);
      const reasons = document.createElement('ul');
      reasons.className = 'guess__reasons';
      g.reasons.forEach(r => {
        const li = document.createElement('li');
        li.textContent = r;
        reasons.appendChild(li);
      });
      guessWrap.appendChild(reasons);
    });
  } else {
    const empty = document.createElement('p');
    empty.className = 'guess__empty';
    empty.textContent = 'اوراقك ناقصه';
    guessWrap.appendChild(empty);
  }
  fingerprintDiv.appendChild(guessWrap);
  box.appendChild(fingerprintDiv);

  document.getElementById('fieldCount').textContent = `(${data.metadata_field_count})`;
  const note = document.getElementById('metadataNote');
  note.textContent = data.metadata_field_count > 0
    ? 'المعلومات اللي طلعها من exiftool'
    : 'مافيه معلومات - يمكن انحذفت بسبب نقل الصورة';

  const groupsWrap = document.getElementById('metadataGroups');
  groupsWrap.innerHTML = '';
  Object.entries(data.metadata_groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .forEach(([group, fields]) => {
      const groupDiv = document.createElement('div');
      groupDiv.className = 'metadata-group';
      const head = document.createElement('div');
      head.className = 'metadata-group__head';
      head.dir = 'ltr';
      head.textContent = `${group.toUpperCase()} · ${fields.length}`;
      groupDiv.appendChild(head);

      const table = document.createElement('table');
      table.className = 'kv-table';
      fields.forEach(f => table.appendChild(kvRow(f.tag, f.value)));
      groupDiv.appendChild(table);

      groupsWrap.appendChild(groupDiv);
    });

  if (data.has_gps) {
    const gpsNote = document.createElement('div');
    gpsNote.className = 'gps-note';
    gpsNote.textContent = 'هذا الملف يحتوي على إحداثيات موقع GPS — مشاركته كما هو تكشف مكان تصويره.';
    groupsWrap.appendChild(gpsNote);
  }
}
