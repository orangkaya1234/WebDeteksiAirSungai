const $ = (id) => document.getElementById(id);
let selectedImage = null;
let selectedName = "";
let lastResult = null;

function setStatus(message, type="") {
  const el = $("status"); el.textContent = message; el.className = `status ${type}`;
}
function setActiveTab(which) {
  $("tab-upload").classList.toggle("active", which === "upload");
  $("tab-dataset").classList.toggle("active", which === "dataset");
  $("upload-pane").classList.toggle("hidden", which !== "upload");
  $("dataset-pane").classList.toggle("hidden", which !== "dataset");
}
$("tab-upload").addEventListener("click", () => setActiveTab("upload"));
$("tab-dataset").addEventListener("click", () => { setActiveTab("dataset"); loadDataset(); });

function selectImage(path, name, sizeText="Siap dianalisis") {
  selectedImage = path; selectedName = name;
  $("file-name").textContent = name;
  $("file-size").textContent = sizeText;
  $("selected-file").classList.remove("hidden");
  $("analyze-btn").disabled = false;
  setStatus("Gambar siap diproses.");
}
function clearSelected() {
  selectedImage = null; selectedName = "";
  $("file-input").value = "";
  $("selected-file").classList.add("hidden");
  $("analyze-btn").disabled = true;
  setStatus("Pilih gambar untuk memulai.");
}
$("remove-file").addEventListener("click", clearSelected);

async function uploadFile(file) {
  if (!file) return;
  const allowed = /\.(jpg|jpeg|png|bmp|tif|tiff|webp)$/i.test(file.name);
  if (!allowed) { setStatus("Format file tidak didukung.", "error"); return; }
  if (file.size > 16 * 1024 * 1024) { setStatus("Ukuran file melebihi 16 MB.", "error"); return; }
  setStatus("Mengunggah gambar...");
  const fd = new FormData(); fd.append("file", file);
  try {
    const response = await fetch("/api/upload", {method:"POST", body:fd});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Upload gagal.");
    selectImage(data.path, data.name, `${(file.size/1024/1024).toFixed(2)} MB · siap dianalisis`);
  } catch (err) { setStatus(err.message, "error"); }
}
$("file-input").addEventListener("change", e => uploadFile(e.target.files[0]));
const dropzone = $("dropzone");
["dragenter","dragover"].forEach(ev => dropzone.addEventListener(ev, e => {e.preventDefault();dropzone.classList.add("dragover");}));
["dragleave","drop"].forEach(ev => dropzone.addEventListener(ev, e => {e.preventDefault();dropzone.classList.remove("dragover");}));
dropzone.addEventListener("drop", e => uploadFile(e.dataTransfer.files[0]));

async function loadDataset() {
  const select = $("dataset-select");
  select.innerHTML = '<option value="">Memuat...</option>';
  try {
    const response = await fetch("/api/images");
    const files = await response.json();
    select.innerHTML = "";
    if (!files.length) {
      select.innerHTML = '<option value="">Belum ada gambar di folder dataset</option>';
      setStatus("Folder dataset belum berisi gambar. Silakan unggah gambar.", "");
      return;
    }
    select.innerHTML = '<option value="">Pilih gambar...</option>';
    files.forEach(path => {
      const opt = document.createElement("option"); opt.value = path; opt.textContent = path; select.appendChild(opt);
    });
  } catch (_) { select.innerHTML = '<option value="">Gagal membaca dataset</option>'; }
}
$("refresh-dataset").addEventListener("click", loadDataset);
$("dataset-select").addEventListener("change", e => {
  if (e.target.value) {
    selectedImage = e.target.value; selectedName = e.target.value.split("/").pop();
    $("selected-file").classList.add("hidden"); $("analyze-btn").disabled = false;
    setStatus(`Dipilih: ${selectedName}`);
  } else { selectedImage = null; $("analyze-btn").disabled = true; }
});

const rangeIds = ["h-min","h-max","s-min","s-max","v-min","v-max"];
rangeIds.forEach(id => $(id).addEventListener("input", () => $(id+"-out").textContent = $(id).value));
function getParams() {
  const val = id => Number($(id).value);
  return {
    image:selectedImage, h_min:val("h-min"), h_max:val("h-max"),
    s_min:val("s-min"), s_max:val("s-max"), v_min:val("v-min"), v_max:val("v-max"),
    kernel:val("kernel"), filter:$("filter").value, ukuran_filter:val("filter-size"),
    cmap:$("cmap").value, normalisasi:$("normalize").checked, balik:$("invert").checked
  };
}
function showResult(data) {
  lastResult = data;
  $("img-original").src = data.asli;
  $("img-mask").src = data.mask;
  $("img-water").src = data.air;
  $("img-false").src = data.false;
  $("image-meta").textContent = `${data.info.nama} · ${data.info.asli} px (asli) · hasil diproses ${data.info.lebar} × ${data.info.tinggi} px`;
  const s = data.stat;
  $("stat-percent").textContent = `${s.persen.toFixed(2)}%`;
  $("stat-progress").style.width = `${Math.max(0,Math.min(100,s.persen))}%`;
  $("stat-pixels").textContent = `${s.pixel_air.toLocaleString("id-ID")} dari ${s.total.toLocaleString("id-ID")} pixel`;
  $("stat-r").textContent = s.r.toFixed(2);
  $("stat-g").textContent = s.g.toFixed(2);
  $("stat-b").textContent = s.b.toFixed(2);
  $("stat-brightness").textContent = s.brightness.toFixed(2);
  $("stat-interpretation").textContent = s.interpretasi;
  $("interpretation-dot").style.background = s.warna;
  $("results").classList.remove("hidden");
}
async function processImage() {
  if (!selectedImage) return;
  const p = getParams();
  if (p.h_min > p.h_max || p.s_min > p.s_max || p.v_min > p.v_max) {
    setStatus("Periksa rentang HSV: nilai minimum tidak boleh melebihi maksimum.", "error"); return;
  }
  $("analyze-btn").disabled = true; $("reprocess-btn").disabled = true;
  setStatus("Sedang memproses citra. Mohon tunggu...");
  try {
    const response = await fetch("/api/process", {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(p)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Proses analisis gagal.");
    showResult(data); setStatus("Analisis selesai. Kamu dapat mengubah parameter dan memproses ulang.", "success");
    $("results").scrollIntoView({behavior:"smooth", block:"start"});
  } catch (err) { setStatus(err.message, "error"); }
  finally { $("analyze-btn").disabled = !selectedImage; $("reprocess-btn").disabled = false; }
}
$("analyze-btn").addEventListener("click", processImage);
$("reprocess-btn").addEventListener("click", processImage);
$("reset-btn").addEventListener("click", () => {
  const defaults = {"h-min":90,"h-max":140,"s-min":30,"s-max":255,"v-min":30,"v-max":200,"kernel":5,"filter-size":5};
  Object.entries(defaults).forEach(([id,v]) => {$(id).value=v;if(id.includes("-min")||id.includes("-max")) $(id+"-out").textContent=v;});
  $("filter").value="Gaussian Blur"; $("cmap").value="COLORMAP_JET"; $("normalize").checked=true; $("invert").checked=true;
  if (selectedImage) setStatus("Parameter dikembalikan ke nilai awal. Klik Terapkan pengaturan untuk menjalankan ulang.");
});
loadDataset();
