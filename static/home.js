const defaultTags = ["学习", "游戏", "音乐", "生活"];

function bindNavActions() {
    const searchBtn = document.getElementById("searchBtn");
    const searchInput = document.getElementById("searchInput");
    if (searchBtn && searchInput) {
        searchBtn.onclick = () => {
            const q = searchInput.value.trim();
            if (q) location.href = `/static/search.html?q=${encodeURIComponent(q)}`;
        };
    }
    const loginBtn = document.getElementById("loginBtn");
    if (loginBtn) loginBtn.onclick = () => location.href = "/static/profile.html";
    const profileBtn = document.getElementById("profileBtn");
    if (profileBtn) profileBtn.onclick = () => location.href = "/static/profile.html";
    const adminBtn = document.getElementById("adminBtn");
    if (adminBtn) adminBtn.onclick = () => location.href = "/static/admin.html";
}

function collectTags(list) {
    const set = new Set();
    list.forEach((v) => {
        (v.tags || "")
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean)
            .forEach((t) => set.add(t));
    });
    return Array.from(set);
}

function renderTags(tags) {
    const row = document.getElementById("tagRow");
    if (!row) return;
    row.innerHTML = "";
    const finalTags = tags.length ? tags : defaultTags;
    finalTags.forEach((tag) => {
        const span = document.createElement("span");
        span.className = "tag-chip";
        span.textContent = tag;
        span.onclick = () => (location.href = `/static/partition.html?cat=${encodeURIComponent(tag)}`);
        row.appendChild(span);
    });
}

async function loadHome() {
    try {
        const rec = await api("/api/recommend");
        const recBox = document.getElementById("recommendList");
        if (recBox) {
            recBox.innerHTML = "";
            rec.forEach((v) => renderVideoCard(recBox, v));
        }

        const latest = await api("/api/videos?order=new");
        const latestBox = document.getElementById("latestList");
        if (latestBox) {
            latestBox.innerHTML = "";
            latest.forEach((v) => renderVideoCard(latestBox, v));
        }

        const tags = collectTags(rec).concat(collectTags(latest));
        renderTags(tags);
    } catch (err) {
        console.error(err);
        alert(err.message);
    }
}

bindNavActions();
loadMeAndRender();
loadHome();
