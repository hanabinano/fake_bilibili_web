// 播放页逻辑：弹幕按时间点显示 + 评论 + 基本信息
const params = new URLSearchParams(location.search);
const VIDEO_ID = Number(params.get("id") || 1);

const video = document.getElementById("videoElement");
const dmLayer = document.getElementById("danmakuLayer");
const dmInput = document.getElementById("dmInput");
const sendBtn = document.getElementById("sendBtn");
const dmColorInput = document.getElementById("dmColor");
const dmListPanel = document.getElementById("commentList");
const commentBtn = document.getElementById("commentBtn");
const commentInput = document.getElementById("commentInput");

let danmakuList = [];
let danmakuIndex = 0;

function syncDanmakuIndex(currentTime) {
    const idx = danmakuList.findIndex((dm) => dm.time >= currentTime);
    danmakuIndex = idx === -1 ? danmakuList.length : idx;
}

function flushDanmaku(currentTime) {
    while (danmakuIndex < danmakuList.length && danmakuList[danmakuIndex].time <= currentTime) {
        const dm = danmakuList[danmakuIndex];
        shootDanmaku(dm.content, dm.color || "#fff");
        danmakuIndex += 1;
    }
}

function shootDanmaku(text, color) {
    const span = document.createElement("span");
    span.innerText = text;
    span.className = "danmaku-item";
    span.style.color = color;
    const top = Math.floor(Math.random() * 80) + "%";
    span.style.top = top;
    const duration = Math.floor(Math.random() * 5) + 5 + "s";
    span.style.animationDuration = duration;
    dmLayer.appendChild(span);
    span.addEventListener("animationend", () => span.remove());
}

async function loadDanmaku() {
    try {
        danmakuList = await api(`/api/videos/${VIDEO_ID}/danmaku`);
        syncDanmakuIndex(video.currentTime);
        renderDanmakuSideList();
    } catch (e) {
        console.error(e);
    }
}

async function sendDanmaku() {
    const content = dmInput.value.trim();
    if (!content) return;
    const localDm = {
        time: video.currentTime,
        content,
        color: dmColorInput.value,
        user_id: "me",
    };
    const idx = insertDanmaku(localDm);
    danmakuIndex = Math.max(danmakuIndex, idx + 1); // 避免立即重复播放
    shootDanmaku(content, dmColorInput.value); // 发送后即时看到弹幕
    try {
        await api(`/api/videos/${VIDEO_ID}/danmaku`, {
            method: "POST",
            body: JSON.stringify({
                content,
                color: dmColorInput.value,
                video_time: video.currentTime,
            }),
        });
        dmInput.value = "";
        // 不立即重载列表，避免指针重置导致重复播放
        renderDanmakuSideList();
    } catch (e) {
        alert(e.message || "发送失败，需登录");
    }
}

async function loadComments() {
    try {
        const data = await api(`/api/videos/${VIDEO_ID}/comments`);
        dmListPanel.innerHTML = "";
        data.forEach((c) => {
            const div = document.createElement("div");
            div.className = "panel";
            div.innerHTML = `<strong>${c.nickname || "用户" + c.user_id}</strong>: ${c.content}`;
            if (c.replies && c.replies.length) {
                c.replies.forEach((r) => {
                    const p = document.createElement("p");
                    p.style.marginLeft = "12px";
                    p.innerText = `↳ ${r.nickname || "用户" + r.user_id}: ${r.content}`;
                    div.appendChild(p);
                });
            }
            dmListPanel.appendChild(div);
        });
    } catch (e) {
        console.error(e);
    }
}

async function sendComment() {
    const content = commentInput.value.trim();
    if (!content) return;
    try {
        await api(`/api/videos/${VIDEO_ID}/comments`, {
            method: "POST",
            body: JSON.stringify({ content }),
        });
        commentInput.value = "";
        loadComments();
    } catch (e) {
        alert(e.message || "请登录后评论");
    }
}

async function loadVideoDetail() {
    const detail = await api(`/api/videos/${VIDEO_ID}`);
    document.getElementById("videoTitle").innerText = detail.title;
    document.getElementById("videoMeta").innerHTML = `
        <span class="stat">播放 ${detail.plays}</span>
        <span class="stat">点赞 ${detail.likes}</span>
        <span class="stat">收藏 ${detail.favorites}</span>
        <span class="stat">投币 ${detail.coins || 0}</span>
        ${detail.tags ? detail.tags.split(',').map(t => `<span class="tag">${t.trim()}</span>`).join('') : ''}
    `;
    // 渲染UP主信息
    const creatorName = document.getElementById("creatorName");
    const creatorDesc = document.getElementById("creatorDesc");
    const creatorAvatar = document.getElementById("creatorAvatar");
    if (creatorName) creatorName.innerText = detail.uploader_name || `UP主 ${detail.uploader_id || ""}`;
    if (creatorDesc) creatorDesc.innerText = detail.description || "欢迎关注，更多精彩视频";
    if (creatorAvatar) creatorAvatar.src = detail.uploader_avatar || DEFAULT_AVATAR;
    video.querySelector("source").src = detail.file_path;
    video.load();
    await api(`/api/videos/${VIDEO_ID}/play`, { method: "POST" });
}

async function loadHighlights() {
    const box = document.getElementById("highlightList");
    if (!box) return;
    try {
        const data = await api(`/api/videos/${VIDEO_ID}/danmaku/highlight`);
        if (!data.length) {
            box.innerHTML = '<span class="meta">暂无高能弹幕</span>';
            return;
        }
        box.innerHTML = data
            .map((d) => `<span class="badge">${formatTime(d.second)} · ${d.count}条</span>`)
            .join("");
    } catch (e) {
        console.error(e);
    }
}

function formatTime(sec) {
    const m = Math.floor(sec / 60)
        .toString()
        .padStart(2, "0");
    const s = Math.floor(sec % 60)
        .toString()
        .padStart(2, "0");
    return `${m}:${s}`;
}

video.addEventListener("timeupdate", () => flushDanmaku(video.currentTime));
video.addEventListener("seeked", () => syncDanmakuIndex(video.currentTime));
video.addEventListener("loadedmetadata", () => syncDanmakuIndex(video.currentTime));
video.addEventListener("pause", () => {
    dmLayer.classList.add("paused");
});
video.addEventListener("play", () => {
    dmLayer.classList.remove("paused");
});
sendBtn.onclick = sendDanmaku;
dmInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") sendDanmaku();
});
commentBtn.onclick = sendComment;

async function boot() {
    if (window.loadMeAndRender) window.loadMeAndRender();
    await loadVideoDetail();
    await loadDanmaku();
    await loadComments();
    await loadHighlights();
}
boot();

function insertDanmaku(dm) {
    const idx = danmakuList.findIndex((item) => item.time > dm.time);
    if (idx === -1) {
        danmakuList.push(dm);
        return danmakuList.length - 1;
    } else {
        danmakuList.splice(idx, 0, dm);
        return idx;
    }
}

function renderDanmakuSideList() {
    const box = document.getElementById("dmSideList");
    if (!box) return;
    box.innerHTML = "";
    danmakuList.forEach((dm) => {
        const div = document.createElement("div");
        div.className = "dm-item";
        div.innerHTML = `
            <span class="time">${formatTime(dm.time || 0)}</span>
            <span class="content" style="color:${dm.color || "#fff"}">${dm.content}</span>
            <span class="user">${dm.nickname || `UID ${dm.user_id || ""}`}</span>
        `;
        box.appendChild(div);
    });
}
