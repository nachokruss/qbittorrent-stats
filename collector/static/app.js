/* ==========================================================================
   qBittorrent Stats — Frontend JavaScript
   ========================================================================== */

(function () {
    "use strict";

    // -----------------------------------------------------------------------
    // Tab switching
    // -----------------------------------------------------------------------

    document.querySelectorAll(".tab").forEach(function (btn) {
        btn.addEventListener("click", function () {
            document.querySelectorAll(".tab").forEach(function (b) { b.classList.remove("active"); });
            document.querySelectorAll(".tab-content").forEach(function (c) { c.classList.remove("active"); });
            btn.classList.add("active");
            document.getElementById(btn.dataset.tab).classList.add("active");
            // Load data for the tab
            var tab = btn.dataset.tab;
            if (tab === "dashboard") loadDashboard();
            else if (tab === "charts") loadChart("daily");
            else if (tab === "torrents") loadTorrents();
            else if (tab === "trackers") loadTrackers();
        });
    });

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------

    function fmtBytes(bytes) {
        if (!bytes || bytes === 0) return "0 B";
        var units = ["B", "KB", "MB", "GB", "TB"];
        var i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(2) + " " + units[i];
    }

    function fmtDate(d) {
        if (!d) return "—";
        var dt = new Date(d);
        return dt.toLocaleDateString() + " " + dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    function fmtDateShort(d) {
        if (!d) return "—";
        return new Date(d).toLocaleDateString();
    }

    // -----------------------------------------------------------------------
    // Dashboard
    // -----------------------------------------------------------------------

    function loadDashboard() {
        fetch("/api/dashboard")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var s = data.stats || {};
                document.getElementById("total-torrents").textContent = s.total_torrents || "—";
                document.getElementById("active-torrents").textContent = s.active_torrents || "—";
                document.getElementById("total-uploaded").textContent = (s.total_uploaded_gb || 0) + " GB";
                document.getElementById("total-size").textContent = (s.total_size_tb || 0) + " TB";
                document.getElementById("total-seeding-days").textContent = (s.total_seeding_days || 0);

                var runEl = document.getElementById("last-run");
                if (data.last_run) {
                    var r = data.last_run;
                    runEl.textContent = "Last collection: " + fmtDate(r.started_at) +
                        " — " + (r.torrents_seen || 0) + " torrents, " + (r.errors || 0) + " errors";
                } else {
                    runEl.textContent = "Last collection: no data yet";
                }
            })
            .catch(function (err) {
                console.error("Dashboard load failed:", err);
            });
    }

    // -----------------------------------------------------------------------
    // Charts
    // -----------------------------------------------------------------------

    var uploadChart = null;
    var chartTrackerGroupsLoaded = false;

    document.querySelectorAll(".chart-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
            document.querySelectorAll(".chart-btn").forEach(function (b) { b.classList.remove("active"); });
            btn.classList.add("active");
            loadChart(btn.dataset.period);
        });
    });

    document.getElementById("chart-tracker-filter").addEventListener("change", function () {
        loadChart(getActivePeriod());
    });

    function getActivePeriod() {
        var activeBtn = document.querySelector(".chart-btn.active");
        return activeBtn ? activeBtn.dataset.period : "daily";
    }

    function populateChartTrackerFilter() {
        if (chartTrackerGroupsLoaded) return;
        chartTrackerGroupsLoaded = true;

        fetch("/api/tracker-groups")
            .then(function (r) { return r.json(); })
            .then(function (groups) {
                var select = document.getElementById("chart-tracker-filter");
                groups.forEach(function (g) {
                    var opt = document.createElement("option");
                    opt.value = g;
                    opt.textContent = g;
                    select.appendChild(opt);
                });
            })
            .catch(function (err) {
                console.error("Tracker groups load failed:", err);
            });
    }

    function loadChart(period) {
        var tracker = document.getElementById("chart-tracker-filter").value;
        var params = new URLSearchParams();
        if (tracker) params.set("tracker", tracker);
        var url = "/api/uploads/" + period + (params.toString() ? "?" + params.toString() : "");
        var labelKey = period === "daily" ? "day" : period === "weekly" ? "week" : "month";

        // Populate tracker dropdown on first chart load
        populateChartTrackerFilter();

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var labels = data.map(function (d) { return fmtDateShort(d[labelKey]); });
                var values = data.map(function (d) { return d.uploaded_gb || 0; });

                if (uploadChart) {
                    uploadChart.destroy();
                }

                var ctx = document.getElementById("upload-chart").getContext("2d");
                uploadChart = new Chart(ctx, {
                    type: "bar",
                    data: {
                        labels: labels,
                        datasets: [{
                            label: "Uploaded (GB)",
                            data: values,
                            backgroundColor: "rgba(74, 144, 217, 0.6)",
                            borderColor: "rgba(74, 144, 217, 1)",
                            borderWidth: 1,
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: { display: true, text: "GB Uploaded" },
                            },
                        },
                    },
                });
            })
            .catch(function (err) {
                console.error("Chart load failed:", err);
            });
    }

    // -----------------------------------------------------------------------
    // Torrents
    // -----------------------------------------------------------------------

    var torrentsPage = 1;
    var currentSort = "name";
    var currentOrder = "asc";

    // Clickable column headers for sorting
    document.querySelectorAll("#torrents-table thead th[data-sort]").forEach(function (th) {
        th.addEventListener("click", function () {
            var sortCol = th.dataset.sort;
            if (currentSort === sortCol) {
                // Toggle order: asc -> desc -> asc
                currentOrder = currentOrder === "asc" ? "desc" : "asc";
            } else {
                currentSort = sortCol;
                currentOrder = "asc";
            }
            updateSortIndicators();
            torrentsPage = 1;
            loadTorrents();
        });
        th.style.cursor = "pointer";
    });

    function updateSortIndicators() {
        document.querySelectorAll("#torrents-table thead th[data-sort]").forEach(function (th) {
            var arrow = th.querySelector(".sort-arrow");
            if (arrow) arrow.remove();
            if (th.dataset.sort === currentSort) {
                var span = document.createElement("span");
                span.className = "sort-arrow";
                span.textContent = currentOrder === "asc" ? " \u25B2" : " \u25BC";
                th.appendChild(span);
            }
        });
    }

    function loadTorrents() {
        var params = new URLSearchParams();
        var search = document.getElementById("search-input").value.trim();
        var tracker = document.getElementById("tracker-filter").value;
        var privacy = document.getElementById("privacy-filter").value;
        var hideDeleted = document.getElementById("hide-deleted").checked;
        var lastSeen = document.getElementById("last-seen-filter").value;

        if (search) params.set("search", search);
        if (tracker) params.set("tracker", tracker);
        if (privacy) params.set("privacy", privacy);
        if (hideDeleted) params.set("show_deleted", "false");
        params.set("last_seen", lastSeen);
        params.set("sort", currentSort);
        params.set("order", currentOrder);
        params.set("page", torrentsPage);

        fetch("/api/torrents?" + params.toString())
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderTorrents(data.torrents);
                renderPagination(data);
                populateTrackerFilter(data.torrents);
            })
            .catch(function (err) {
                console.error("Torrents load failed:", err);
            });
    }

    function renderTorrents(torrents) {
        var tbody = document.getElementById("torrents-body");
        tbody.innerHTML = "";

        torrents.forEach(function (t) {
            var tr = document.createElement("tr");

            var privacyClass = t.privacy === "private" ? "badge-private" : "badge-public";
            var stateText = t.removed_at ? "Removed" : (t.last_state || "—");
            var stateClass = t.removed_at ? "badge-removed" : privacyClass;

            tr.innerHTML =
                '<td><a class="torrent-name-link" data-hash="' + escapeHtml(t.torrent_hash) + '">' + escapeHtml(t.name) + '</a></td>' +
                '<td>' + escapeHtml(t.tracker_group) + '</td>' +
                '<td><span class="badge ' + privacyClass + '">' + escapeHtml(t.privacy) + '</span></td>' +
                '<td><span class="badge ' + stateClass + '">' + escapeHtml(stateText) + '</span></td>' +
                '<td>' + (t.uploaded_gb || 0) + ' GB</td>' +
                '<td>' + (t.seeding_days || 0) + '</td>' +
                '<td>' + fmtDateShort(t.last_seen_at) + '</td>';

            tbody.appendChild(tr);
        });

        // Bind click handlers on torrent name links
        tbody.querySelectorAll(".torrent-name-link").forEach(function (link) {
            link.addEventListener("click", function () {
                showTorrentDetails(link.dataset.hash);
            });
        });
    }

    function renderPagination(data) {
        var el = document.getElementById("pagination");
        el.innerHTML = "";

        var prevBtn = document.createElement("button");
        prevBtn.textContent = "Previous";
        prevBtn.disabled = data.page <= 1;
        prevBtn.addEventListener("click", function () {
            torrentsPage--;
            loadTorrents();
        });

        var nextBtn = document.createElement("button");
        nextBtn.textContent = "Next";
        nextBtn.disabled = data.page >= data.total_pages;
        nextBtn.addEventListener("click", function () {
            torrentsPage++;
            loadTorrents();
        });

        var info = document.createElement("span");
        info.textContent = "Page " + data.page + " of " + data.total_pages + " (" + data.total + " total)";

        el.appendChild(prevBtn);
        el.appendChild(info);
        el.appendChild(nextBtn);
    }

    var trackerFilterPopulated = false;
    function populateTrackerFilter(torrents) {
        if (trackerFilterPopulated) return;
        trackerFilterPopulated = true;

        var select = document.getElementById("tracker-filter");
        var groups = {};
        torrents.forEach(function (t) {
            if (t.tracker_group) groups[t.tracker_group] = true;
        });
        Object.keys(groups).sort().forEach(function (g) {
            var opt = document.createElement("option");
            opt.value = g;
            opt.textContent = g;
            select.appendChild(opt);
        });
    }

    // Filter change handlers
    document.getElementById("search-input").addEventListener("input", function () {
        torrentsPage = 1;
        loadTorrents();
    });
    document.getElementById("tracker-filter").addEventListener("change", function () {
        torrentsPage = 1;
        loadTorrents();
    });
    document.getElementById("privacy-filter").addEventListener("change", function () {
        torrentsPage = 1;
        loadTorrents();
    });
    document.getElementById("hide-deleted").addEventListener("change", function () {
        torrentsPage = 1;
        loadTorrents();
    });
    document.getElementById("last-seen-filter").addEventListener("change", function () {
        torrentsPage = 1;
        loadTorrents();
    });

    // -----------------------------------------------------------------------
    // Trackers
    // -----------------------------------------------------------------------

    function loadTrackers() {
        fetch("/api/trackers")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var tbody = document.getElementById("trackers-body");
                tbody.innerHTML = "";

                data.forEach(function (t) {
                    var tr = document.createElement("tr");
                    tr.innerHTML =
                        '<td>' + escapeHtml(t.tracker_group) + '</td>' +
                        '<td>' + t.torrent_count + '</td>' +
                        '<td>' + (t.uploaded_gb || 0) + ' GB</td>';
                    tbody.appendChild(tr);
                });
            })
            .catch(function (err) {
                console.error("Trackers load failed:", err);
            });
    }

    // -----------------------------------------------------------------------
    // Torrent Details Modal
    // -----------------------------------------------------------------------

    var detailChart = null;

    function showTorrentDetails(hash) {
        var modal = document.getElementById("torrent-modal");
        modal.classList.add("active");

        // Show loading state
        document.getElementById("modal-torrent-name").textContent = "Loading...";
        document.getElementById("detail-grid").innerHTML = '<p>Loading details...</p>';
        document.getElementById("detail-trackers-body").innerHTML = "";
        document.getElementById("detail-events-body").innerHTML = "";
        if (detailChart) { detailChart.destroy(); detailChart = null; }

        fetch("/api/torrents/" + encodeURIComponent(hash))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderTorrentDetails(data);
            })
            .catch(function (err) {
                console.error("Torrent details load failed:", err);
                document.getElementById("modal-torrent-name").textContent = "Error loading details";
                document.getElementById("detail-grid").innerHTML = '<p style="color:red">Failed to load torrent details.</p>';
            });
    }

    function hideTorrentDetails() {
        var modal = document.getElementById("torrent-modal");
        modal.classList.remove("active");
        if (detailChart) { detailChart.destroy(); detailChart = null; }
    }

    // Close button and overlay click
    document.getElementById("modal-close").addEventListener("click", hideTorrentDetails);
    document.querySelector(".modal-overlay").addEventListener("click", hideTorrentDetails);

    function renderTorrentDetails(data) {
        var t = data.torrent;

        // Title
        document.getElementById("modal-torrent-name").textContent = t.name || "Unknown";

        // Info grid
        var grid = document.getElementById("detail-grid");
        var items = [
            { label: "Tracker", value: t.tracker_group || "—" },
            { label: "Privacy", value: t.privacy || "—" },
            { label: "State", value: t.last_state || "—" },
            { label: "Size", value: (t.size_gb || 0) + " GB" },
            { label: "Total Uploaded", value: (t.uploaded_total_gb || 0) + " GB" },
            { label: "Total Downloaded", value: (t.downloaded_total_gb || 0) + " GB" },
            { label: "Seeding Days", value: (t.seeding_days || 0) },
            { label: "Seeds / Leeches", value: (t.num_seeds || "—") + " / " + (t.num_leechs || "—") },
            { label: "First Seen", value: fmtDate(t.first_seen_at) },
            { label: "Last Seen", value: fmtDate(t.last_seen_at) },
            { label: "Category", value: t.category || "—" },
            { label: "Tags", value: t.tags || "—" },
        ];
        grid.innerHTML = items.map(function (item) {
            return '<div class="detail-item">' +
                '<div class="detail-label">' + item.label + '</div>' +
                '<div class="detail-value">' + escapeHtml(String(item.value)) + '</div>' +
                '</div>';
        }).join("");

        // Upload/Download chart from history
        var history = data.history || [];
        if (history.length > 0) {
            var labels = history.map(function (h) { return fmtDateShort(h.day); });
            var uploaded = history.map(function (h) { return h.uploaded_gb || 0; });
            var downloaded = history.map(function (h) { return h.downloaded_gb || 0; });

            if (detailChart) { detailChart.destroy(); }
            var ctx = document.getElementById("detail-chart").getContext("2d");
            detailChart = new Chart(ctx, {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: "Uploaded (GB)",
                            data: uploaded,
                            borderColor: "rgba(74, 144, 217, 1)",
                            backgroundColor: "rgba(74, 144, 217, 0.1)",
                            fill: true,
                            tension: 0.3,
                        },
                        {
                            label: "Downloaded (GB)",
                            data: downloaded,
                            borderColor: "rgba(217, 74, 74, 1)",
                            backgroundColor: "rgba(217, 74, 74, 0.1)",
                            fill: true,
                            tension: 0.3,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: { display: true, text: "GB" },
                        },
                    },
                },
            });
        }

        // Trackers table
        var trackersBody = document.getElementById("detail-trackers-body");
        trackersBody.innerHTML = "";
        (data.trackers || []).forEach(function (tr) {
            var row = document.createElement("tr");
            row.innerHTML =
                '<td title="' + escapeHtml(tr.tracker_url || "") + '">' + escapeHtml(tr.tracker_url || "—") + '</td>' +
                '<td>' + escapeHtml(tr.tracker_group || "—") + '</td>' +
                '<td>' + (tr.status != null ? tr.status : "—") + '</td>' +
                '<td>' + (tr.num_peers != null ? tr.num_peers : "—") + '</td>' +
                '<td>' + (tr.num_seeds != null ? tr.num_seeds : "—") + '</td>' +
                '<td>' + (tr.num_leeches != null ? tr.num_leeches : "—") + '</td>';
            trackersBody.appendChild(row);
        });

        // Events table
        var eventsBody = document.getElementById("detail-events-body");
        eventsBody.innerHTML = "";
        (data.events || []).forEach(function (ev) {
            var row = document.createElement("tr");
            var detailsStr = "";
            if (ev.details) {
                try { detailsStr = typeof ev.details === "string" ? ev.details : JSON.stringify(ev.details); } catch (e) { detailsStr = String(ev.details); }
            }
            row.innerHTML =
                '<td>' + fmtDate(ev.event_at) + '</td>' +
                '<td>' + escapeHtml(ev.event_type || "—") + '</td>' +
                '<td title="' + escapeHtml(detailsStr) + '">' + escapeHtml(detailsStr) + '</td>';
            eventsBody.appendChild(row);
        });
    }

    // -----------------------------------------------------------------------
    // Utility
    // -----------------------------------------------------------------------

    function escapeHtml(str) {
        if (!str) return "";
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // -----------------------------------------------------------------------
    // Initial load
    // -----------------------------------------------------------------------

    loadDashboard();
})();
