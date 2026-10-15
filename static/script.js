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

const VIDEO_EXT = /\.(mp4|mov|m4v|3gp|avi|mkv|webm)$/i;
const previewVideo = document.getElementById('previewVideo');
let previewUrl = null;

function isVideoFile(file) {
  return (file.type && file.type.startsWith('video/')) || VIDEO_EXT.test(file.name);
}

function selectFile(file) {
  if (!file) return;
  selectedFile = file;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);

  if (isVideoFile(file)) {
    previewImg.hidden = true;
    previewVideo.hidden = false;
    previewVideo.src = previewUrl;
  } else {
    previewVideo.hidden = true;
    previewVideo.removeAttribute('src');
    previewImg.hidden = false;
    previewImg.src = previewUrl;
  }

  const sizeText = file.size >= 1024 * 1024
    ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
    : `${(file.size / 1024).toFixed(0)} KB`;
  previewName.textContent = `${file.name} · ${sizeText}`;
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
    if (!res.ok) throw new Error(data.detail || 'تعذّر تحليل هذا الملف.');
    renderReport(data);
    showOnly(report);
  } catch (err) {
    errorBox.textContent = err.message || 'حدث خطأ غير متوقع أثناء تحليل الملف.';
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
    box.appendChild(highlightCard('مكان التصوير', 'لا توجد بيانات موقع', { muted: true }));
  }

  // تاريخ التصوير
  box.appendChild(
    h.captured_at
      ? highlightCard('تاريخ التصوير', h.captured_at)
      : highlightCard('تاريخ التصوير', 'غير متوفر', { muted: true })
  );

  // الجهاز
  box.appendChild(
    h.device
      ? highlightCard('جهاز التصوير', h.device)
      : highlightCard('جهاز التصوير', 'غير متوفر', { muted: true })
  );

  // الجودة / المواصفات
  const q = h.quality || {};
  if (q.kind === 'video') {
    const main = [];
    if (q.dimensions) main.push(`${q.dimensions.width} × ${q.dimensions.height}`);
    if (q.fps) main.push(`${q.fps} fps`);
    if (main.length) {
      const sub = document.createTextNode(
        [q.duration ? `المدة ${q.duration}` : null, q.codec, q.bitrate, q.file_size].filter(Boolean).join(' · ')
      );
      box.appendChild(highlightCard('مواصفات الفيديو', main.join(' · '), { sub }));
    } else {
      box.appendChild(highlightCard('مواصفات الفيديو', 'غير متوفر', { muted: true }));
    }
    return;
  }
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

function fingerprintRows(rows) {
  const wrap = document.createDocumentFragment();
  rows.forEach(([k, v]) => {
    const row = document.createElement('div');
    row.className = 'fingerprint__row';
    const left = document.createElement('span');
    left.textContent = k;
    const right = document.createElement('span');
    right.dir = 'ltr';
    right.textContent = v;
    row.append(left, right);
    wrap.appendChild(row);
  });
  return wrap;
}

function guessesBlock(guesses, emptyText) {
  const guessWrap = document.createElement('div');
  guessWrap.className = 'guess';
  if (guesses && guesses.length) {
    const heading = document.createElement('div');
    heading.className = 'report__field-label';
    heading.style.marginBottom = '8px';
    heading.textContent = 'الأصل المحتمل (تخمين تقريبي، غير قطعي)';
    guessWrap.appendChild(heading);

    guesses.forEach(g => {
      const item = document.createElement('div');
      item.className = 'guess__item';
      const name = document.createElement('span');
      name.className = 'guess__name';
      name.textContent = g.name;
      const conf = document.createElement('span');
      conf.className = 'guess__confidence';
      conf.textContent = `ثقة ${g.confidence}`;
      item.append(name, conf);
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
    empty.textContent = emptyText;
    guessWrap.appendChild(empty);
  }
  return guessWrap;
}

function buildImageFingerprint(fp) {
  const div = document.createElement('div');
  div.className = 'fingerprint';
  div.appendChild(fingerprintRows([
    ['الصيغة', fp.format || '—'],
    ['الأبعاد', fp.dimensions ? `${fp.dimensions.width} × ${fp.dimensions.height}px` : '—'],
    ['نوع ضغط الألوان (Chroma subsampling)', fp.subsampling || '—'],
    ['جودة JPEG المقدَّرة', fp.estimated_jpeg_quality ? `~${fp.estimated_jpeg_quality}%` : 'غير متاح'],
  ]));
  div.appendChild(guessesBlock(fp.guesses, 'لا توجد مؤشرات كافية في بيانات الصورة لتخمين تطبيق مصدرها.'));
  return div;
}

function buildVideoFingerprint(fp) {
  const v = fp.video || {};
  const a = fp.audio || {};
  const rows = [
    ['الحاوية', fp.container ? `${fp.container}${fp.major_brand ? ` (${fp.major_brand})` : ''}` : '—'],
    ['المدة', fp.duration || '—'],
    ['ترميز الفيديو', v.codec ? `${v.codec}${v.profile ? ` · ${v.profile}` : ''}` : '—'],
    ['الأبعاد', v.width ? `${v.width} × ${v.height}px` : '—'],
    ['معدل الإطارات', v.fps ? `${v.fps} fps` : '—'],
    ['معدل البيانات الكلي', fp.overall_bitrate || '—'],
    ['ترميز الصوت', a.codec ? `${a.codec}${a.channels ? ` · ${a.channels}ch` : ''}${a.sample_rate ? ` · ${a.sample_rate}Hz` : ''}` : 'لا يوجد مسار صوتي'],
    ['المشفّر المسجَّل', fp.encoder || '—'],
  ];
  if (v.rotation) rows.splice(4, 0, ['زاوية الدوران', `${v.rotation}°`]);

  const div = document.createElement('div');
  div.className = 'fingerprint';
  div.appendChild(fingerprintRows(rows));

  if (fp.indicators && fp.indicators.length) {
    const title = document.createElement('div');
    title.className = 'report__field-label indicators__title';
    title.textContent = 'ما تقوله بنية الملف';
    const list = document.createElement('ul');
    list.className = 'indicators';
    fp.indicators.forEach(t => {
      const li = document.createElement('li');
      li.textContent = t;
      list.appendChild(li);
    });
    div.append(title, list);
  }

  div.appendChild(guessesBlock(fp.guesses, 'لا توجد مؤشرات كافية في بنية الفيديو لتخمين مصدره.'));
  return div;
}

const REQUIRED_IDS = [
  'exhibitId', 'analyzedAt', 'reportFileName', 'highlightsBox', 'hashTable',
  'fingerprintBox', 'fingerprintNote', 'fieldCount', 'metadataNote', 'metadataGroups',
];

function assertPageMatchesScript() {
  const missing = REQUIRED_IDS.filter(id => !document.getElementById(id));
  if (missing.length) {
    throw new Error(
      `ملف index.html في الموقع غير متطابق مع script.js — العناصر المفقودة: ${missing.join(', ')}. ` +
      'ارفع الملفين معًا من النسخة الأخيرة ثم حدّث الصفحة بقوة (Ctrl+Shift+R).'
    );
  }
}

function renderReport(data) {
  assertPageMatchesScript();
  document.getElementById('exhibitId').textContent = randomRef('EXH');
  document.getElementById('analyzedAt').textContent = new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  document.getElementById('reportFileName').textContent = data.file_name;

  renderHighlights(data.highlights || {});

  const hashTable = document.getElementById('hashTable');
  hashTable.innerHTML = '';
  Object.entries(data.hashes).forEach(([k, v]) => hashTable.appendChild(kvRow(k.toUpperCase(), v)));

  const box = document.getElementById('fingerprintBox');
  box.innerHTML = '';
  if (data.media_type === 'video') {
    document.getElementById('fingerprintNote').textContent =
      'مستخرج من بنية ملف الفيديو نفسها (الحاوية، المشفّر، الترميز)، فيستمر بالعمل حتى لو حُذفت بيانات الكاميرا والموقع.';
    box.appendChild(buildVideoFingerprint(data.video_fingerprint || {}));
  } else {
    document.getElementById('fingerprintNote').textContent =
      'مستخرج من طبقة الضغط في الصورة نفسها، فيستمر بالعمل حتى لو حُذفت كل البيانات الوصفية بالأسفل.';
    box.appendChild(buildImageFingerprint(data.fingerprint || {}));
  }

  document.getElementById('fieldCount').textContent = `(${data.metadata_field_count})`;
  const note = document.getElementById('metadataNote');
  note.textContent = data.metadata_field_count > 0
    ? 'كل الحقول التي استطاع ExifTool قراءتها من الملف، مجمّعة كما تُخزَّن أصلًا.'
    : 'لم يتم العثور على أي بيانات وصفية — يُحتمل أنها حُذفت عند التصدير أو الرفع.';

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
