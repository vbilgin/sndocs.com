(async function () {
  try {
    const response = await fetch("/versions.json");
    if (!response.ok) return;
    const data = await response.json();
    const current = location.pathname.split("/")[1];
    const select = document.createElement("select");
    select.className = "family-selector";
    select.setAttribute("aria-label", "Documentation release");
    for (const version of data.versions) {
      const option = document.createElement("option");
      option.value = version.path;
      option.textContent = version.title + (version.archived ? " (archived)" : "");
      option.selected = version.family === current;
      select.appendChild(option);
    }
    select.addEventListener("change", () => { location.href = select.value; });
    const header = document.querySelector(".md-header__inner");
    if (header) header.appendChild(select);
  } catch (_) { /* The version manifest is optional in local previews. */ }
})();

