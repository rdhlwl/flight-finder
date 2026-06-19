const GROUPS = {
  bay_area: { label: "Bay Area + Sacramento", airports: ["SFO", "OAK", "SJC", "SMF"] },
  nyc: { label: "New York City", airports: ["JFK", "EWR", "LGA"] },
};

let allDeals = [];
let sortKey = "price";
let sortAsc = true;

function airportGroup(code) {
  for (const [key, g] of Object.entries(GROUPS)) {
    if (g.airports.includes(code)) return key;
  }
  return null;
}

function applyFiltersAndRender() {
  const groupFilter = document.getElementById("group-filter").value;
  const showNear = document.getElementById("show-near").checked;
  const maxPrice = parseFloat(document.getElementById("max-price").value) || Infinity;

  let rows = allDeals.filter(d => {
    if (!showNear && d.match_type === "near") return false;
    if (d.price > maxPrice) return false;
    if (groupFilter && airportGroup(d.origin) !== groupFilter) return false;
    return true;
  });

  rows.sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av === bv) return 0;
    const cmp = av < bv ? -1 : 1;
    return sortAsc ? cmp : -cmp;
  });

  const body = document.getElementById("results-body");
  body.innerHTML = "";
  if (rows.length === 0) {
    body.innerHTML = '<tr><td colspan="9">No deals match these filters yet.</td></tr>';
    return;
  }
  for (const d of rows) {
    const tr = document.createElement("tr");
    if (d.match_type === "near") tr.className = "near-match";
    tr.innerHTML = `
      <td class="price">$${Math.round(d.price)}</td>
      <td>${d.origin} &rarr; ${d.destination}</td>
      <td>${d.depart_date}</td>
      <td>${d.return_date || ""}</td>
      <td>${d.outbound_departure_time || ""}</td>
      <td>${d.outbound_arrival_time || ""}</td>
      <td>${d.duration_label || ""}</td>
      <td><span class="badge ${d.match_type === "near" ? "near" : ""}">${d.match_type}</span></td>
      <td>${(d.scanned_at || "").slice(0, 16).replace("T", " ")}</td>
    `;
    body.appendChild(tr);
  }
}

function init(data) {
  allDeals = data.deals || [];
  document.getElementById("updated-at").textContent = data.updated_at
    ? `Last scan: ${data.updated_at.slice(0, 16).replace("T", " ")} UTC`
    : "No scans yet.";

  document.getElementById("group-filter").addEventListener("change", applyFiltersAndRender);
  document.getElementById("show-near").addEventListener("change", applyFiltersAndRender);
  document.getElementById("max-price").addEventListener("input", applyFiltersAndRender);

  document.querySelectorAll("th[data-sort]").forEach(th => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sortKey === key) {
        sortAsc = !sortAsc;
      } else {
        sortKey = key;
        sortAsc = true;
      }
      applyFiltersAndRender();
    });
  });

  applyFiltersAndRender();
}

fetch("data/scans.json")
  .then(r => r.json())
  .then(init)
  .catch(e => {
    document.getElementById("updated-at").textContent = "Could not load scan data: " + e;
  });
