// 前端通用工具 & API 辅助
const API_BASE = "";
const DEFAULT_AVATAR =
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%2300a1d6'/%3E%3Ccircle cx='32' cy='24' r='12' fill='%23fff'/%3E%3Cpath d='M12 56c4-10 12-16 20-16s16 6 20 16' fill='%23fff'/%3E%3C/svg%3E";

function getToken() {
    return localStorage.getItem("token") || "";
}

function setToken(token) {
    localStorage.setItem("token", token);
}

async function api(path, options = {}) {
    const headers = options.headers || {};
    const token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
    const res = await fetch(API_BASE + path, { ...options, headers });
    if (!res.ok) throw new Error(`网络异常(${res.status})`);
    const data = await res.json();
    if (data.code !== 0) throw new Error(data.message || "接口错误");
    return data.data;
}

function renderVideoCard(container, video) {
    const div = document.createElement("div");
    div.className = "video-card";
    div.innerHTML = `
        <a href="/static/video.html?id=${video.id}">
            <img src="${video.cover || "/static/1.jpg"}" alt="cover">
        </a>
        <div class="info">
            <div class="title">${video.title}</div>
            <div class="meta">播放 ${video.plays || 0} · 点赞 ${video.likes || 0}</div>
            <div class="meta">标签：${video.tags || ""}</div>
        </div>`;
    container.appendChild(div);
}

function renderUserUI(user) {
    const loginBtn = document.getElementById("loginBtn");
    const avatar = document.getElementById("userAvatar");
    if (!loginBtn || !avatar) return;
    if (user) {
        loginBtn.style.display = "none";
        avatar.src = user.avatar || DEFAULT_AVATAR;
        avatar.classList.add("show");
        avatar.onclick = () => (location.href = "/static/profile.html");
    } else {
        avatar.classList.remove("show");
        avatar.onclick = null;
        loginBtn.style.display = "inline-block";
    }
}

async function loadMeAndRender() {
    const token = getToken();
    if (!token) {
        renderUserUI(null);
        return;
    }
    try {
        const me = await api("/api/auth/me");
        renderUserUI(me);
    } catch (e) {
        renderUserUI(null);
    }
}

window.renderUserUI = renderUserUI;
window.loadMeAndRender = loadMeAndRender;
