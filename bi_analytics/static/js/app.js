/* Circuli - Dashboard Application */

const API_BASE = "";
const REFRESH_INTERVAL = 30000;

async function fetchJSON(url) {
    try {
        const response = await fetch(API_BASE + url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`[Circuli] Fetch error for ${url}:`, error);
        return null;
    }
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = value;
    }
}

async function updateDashboardCards() {
    const detections = await fetchJSON("/api/v1/detections?days=1");
    if (detections && detections.data && detections.data.length > 0) {
        const latest = detections.data[detections.data.length - 1];
        setText("total-vehicles", (latest.total_vehicles || 0).toLocaleString());
        setText("active-streams", latest.active_streams || 0);
        setText("parking-spots", latest.parked_vehicles || 0);
    } else {
        setText("total-vehicles", "0");
        setText("active-streams", "0");
        setText("parking-spots", "0");
    }

    const parking = await fetchJSON("/api/v1/analytics/parking");
    if (parking && parking.recommendations) {
        const totalAvailable = parking.recommendations.reduce(
            (sum, r) => sum + (r.available_spots || 0),
            0
        );
        setText("parking-spots", totalAvailable.toLocaleString());
    }
}

async function updateStreams() {
    const container = document.getElementById("streams-container");
    if (!container) return;

    const data = await fetchJSON("/api/v1/streams");
    if (!data || !data.streams) {
        container.innerHTML = '<p class="loading">Unable to load streams.</p>';
        return;
    }

    container.innerHTML = data.streams
        .map(
            (stream) => `
        <div class="stream-card">
            <div class="stream-info">
                <span class="stream-name">${escapeHtml(stream.name)}</span>
                <span class="stream-url">${escapeHtml(stream.url)}</span>
            </div>
            <span class="stream-status ${stream.status === "active" ? "active" : "inactive"}">
                ${stream.status === "active" ? "● Active" : "○ Inactive"}
            </span>
        </div>
    `
        )
        .join("");
}

async function updateAnalytics() {
    const traffic = await fetchJSON("/api/v1/analytics/traffic?days=7");
    const trafficEl = document.getElementById("analytics-traffic");
    if (trafficEl) {
        if (traffic && traffic.volume_by_hour && traffic.volume_by_hour.length > 0) {
            const totalVehicles = traffic.volume_by_hour.reduce(
                (sum, h) => sum + (h.total_vehicles || 0),
                0
            );
            const peakHour = traffic.volume_by_hour.reduce((max, h) =>
                (h.total_vehicles || 0) > (max.total_vehicles || 0) ? h : max
            );
            trafficEl.textContent = `${totalVehicles.toLocaleString()} vehicles detected this week. Peak hour: ${peakHour.hour}:00.`;
        } else {
            trafficEl.textContent = "No traffic data available.";
        }
    }

    const parking = await fetchJSON("/api/v1/analytics/parking");
    const parkingEl = document.getElementById("analytics-parking");
    if (parkingEl) {
        if (parking && parking.recommendations && parking.recommendations.length > 0) {
            const top = parking.recommendations[0];
            parkingEl.textContent = `Best: ${top.location} (score: ${top.score}, ${top.available_spots} spots available).`;
        } else {
            parkingEl.textContent = "No parking recommendations available.";
        }
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(text || ""));
    return div.innerHTML;
}

async function refreshAll() {
    await Promise.all([updateDashboardCards(), updateStreams(), updateAnalytics()]);
}

document.addEventListener("DOMContentLoaded", () => {
    refreshAll();
    setInterval(refreshAll, REFRESH_INTERVAL);
});
