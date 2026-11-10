const api = (path, opts) => fetch(window.CAP_API_BASE + path, {headers: {"Content-Type": "application/json"}, ...opts}).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e.error || r.status)));
const view = document.getElementById("view");
const esc = (s) => { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; };
const money = (n) => "$" + Number(n).toLocaleString();
let cache = [];

async function home(q = "", country = "") {
  const params = new URLSearchParams(); if (q) params.set("q", q); if (country) params.set("country", country);
  const {items} = await api("/destinations?" + params);
  cache = items;
  const countries = [...new Set(items.map(d => d.country))].sort();
  view.innerHTML = `
    <div class="toolbar">
      <input id="q" placeholder="Search trips..." value="${esc(q)}">
      <select id="country"><option value="">All countries</option>${countries.map(c => `<option ${c === country ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>
    </div>
    <div class="grid">
      ${items.map(d => `
        <article class="card" data-id="${d.id}">
          <div class="art" style="background:${esc(d.gradient)}"></div>
          <div class="body"><h3>${esc(d.name)}</h3>
          <p class="meta">${esc(d.country)} · ★ ${d.rating}</p>
          <p>${esc(d.blurb)}</p>
          <p class="price">from ${money(d.price)} / person</p></div>
        </article>`).join("") || "<p>No trips match — try clearing the search.</p>"}
    </div>`;
  const search = document.getElementById("q"); const select = document.getElementById("country");
  search.onchange = () => home(search.value, select.value);
  select.onchange = () => home(search.value, select.value);
  view.querySelectorAll(".card").forEach(c => c.onclick = () => location.hash = "#/trip/" + c.dataset.id);
}

async function trip(id) {
  const d = cache.find(x => x.id === id) || await api("/destinations/" + encodeURIComponent(id));
  view.innerHTML = `
    <p><a href="#/">&larr; all destinations</a></p>
    <div class="detail">
      <div class="art" style="background:${esc(d.gradient)}"></div>
      <h2>${esc(d.name)}</h2>
      <p class="meta">${esc(d.country)} · ★ ${d.rating} · <span class="price">${money(d.price)} / person</span></p>
      <p>${esc(d.blurb)}</p>
      <h3>Book this trip</h3>
      <form id="book">
        <input id="name" placeholder="Your name" required>
        <input id="email" type="email" placeholder="Email" required>
        <input id="date" type="date" required>
        <input id="travelers" type="number" min="1" max="12" value="2" required>
        <button>Book — total <span id="total">${money(d.price * 2)}</span></button>
      </form>
      <p id="done" class="meta"></p>
    </div>`;
  const travelers = document.getElementById("travelers");
  travelers.oninput = () => document.getElementById("total").textContent = money(d.price * Number(travelers.value || 0));
  document.getElementById("book").onsubmit = async (e) => {
    e.preventDefault();
    const booking = await api("/bookings", {method: "POST", body: JSON.stringify({destinationId: d.id, name: name.value, email: email.value, date: date.value, travelers: Number(travelers.value)})});
    document.getElementById("done").textContent = `Booked! Reference ${booking.id.slice(0, 8)} — total ${money(booking.total)}. Find it under My trips.`;
  };
}

async function trips() {
  const email = localStorage.getItem("wanderly-email") || "";
  view.innerHTML = `
    <h2>My trips</h2>
    <form id="lookup"><input id="email" type="email" placeholder="Email used at booking" value="${esc(email)}" required><button>Look up</button></form>
    <div id="mine"></div>`;
  document.getElementById("lookup").onsubmit = async (e) => {
    e.preventDefault();
    localStorage.setItem("wanderly-email", email.value);
    const {items} = await api("/bookings?email=" + encodeURIComponent(email.value));
    document.getElementById("mine").innerHTML = items.map(b => `
      <div class="booking"><strong>${esc(b.destinationId)}</strong> · ${esc(b.date)} · ${b.travelers} traveler(s) · ${money(b.total)}<br>
      <span class="meta">reference ${b.id.slice(0, 8)} · booked for ${esc(b.name)}</span></div>`).join("") || "<p>No bookings for that email yet.</p>";
  };
  if (email) document.getElementById("lookup").requestSubmit();
}

function route() {
  const m = location.hash.match(/^#\/trip\/(.+)$/);
  if (m) return trip(decodeURIComponent(m[1]));
  if (location.hash === "#/trips") return trips();
  return home();
}
window.addEventListener("hashchange", route); route();
