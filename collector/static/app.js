/* ==========================================================================
   qBittorrent Stats — Frontend JavaScript
   ========================================================================== */

(function () {
    "use strict";

    // -----------------------------------------------------------------------
    // Tab switching with URL hash routing
    // -----------------------------------------------------------------------

    var tabLoaders = {
        "dashboard": loadDashboard,
        "charts": function () { loadChart("daily"); },
        "torrents": loadTorrents,
        "trackers": loadTrackers,
        "top-uploads": loadTop5Daily,
        "efficiency": loadEfficiency
    };

    function switchTab(tabName) {
        // Update UI
        document.querySelectorAll(".tab").forEach(function (b) { b.classList.remove("active"); });
        document.querySelectorAll(".tab-content").forEach(function (c) { c.classList.remove("active"); });

        var btn = document.querySelector('.tab[data-tab="' + tabName + '"]');
        var section = document.getElementById(tabName);
        if (btn) btn.classList.add("active");
        if (section) section.classList.add("active");

        // Load data for the tab
        var loader = tabLoaders[tabName];
        if (loader) loader();
    }

    function navigateTo(tabName) {
        // Update URL hash without triggering hashchange
        if (location.hash !== "#" + tabName) {
            history.pushState(null, "", "#" + tabName);
        }
        switchTab(tabName);
    }

    // Handle tab button clicks
    document.querySelectorAll(".tab").forEach(function (btn) {
        btn.addEventListener("click", function () {
            navigateTo(btn.dataset.tab);
        });
    });

    // Handle browser back/forward buttons
    window.addEventListener("hashchange", function () {
        var hash = location.hash.replace("#", "");
        if (hash && tabLoaders[hash]) {
            switchTab(hash);
        } else {
            navigateTo("dashboard");
        }
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
                document.getElementById("active-torrents").textContent = s.active_torrents || "—";
                document.getElementById("total-uploaded").textContent = (s.total_uploaded_gb || 0) + " GB";
                document.getElementById("total-size").textContent = (s.total_size_tb || 0) + " TB";

                var runEl = document.getElementById("last-run");
                if (data.error) {
                    runEl.textContent = "Last collection: " + data.error;
                } else if (data.last_run) {
                    var r = data.last_run;
                    runEl.textContent = "Last collection: " + fmtDate(r.started_at) +
                        " — " + (r.torrents_seen || 0) + " torrents, " + (r.errors || 0) + " errors";
                } else {
                    runEl.textContent = "Last collection: no data yet";
                }
            })
            .catch(function (err) {
                console.error("Dashboard load failed:", err);
                document.getElementById("last-run").textContent = "Last collection: error connecting to server";
            });
    }

    // -----------------------------------------------------------------------
    // Charts
    // -----------------------------------------------------------------------

    var uploadChart = null;
    var chartTrackerGroupsLoaded = false;
    var isByTrackerMode = document.getElementById("chart-by-tracker-btn").classList.contains("active");

    document.querySelectorAll(".chart-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
            document.querySelectorAll(".chart-btn").forEach(function (b) { b.classList.remove("active"); });
            btn.classList.add("active");
            loadChart(btn.dataset.period);
        });
    });

    function updateChartFilterVisibility() {
        document.getElementById("chart-tracker-filter").style.display = isByTrackerMode ? "none" : "";
    }

    document.getElementById("chart-by-tracker-btn").addEventListener("click", function () {
        isByTrackerMode = !isByTrackerMode;
        this.classList.toggle("active", isByTrackerMode);
        updateChartFilterVisibility();
        loadChart(getActivePeriod());
    });

    // Set initial visibility
    updateChartFilterVisibility();

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
        // Populate tracker dropdown on first chart load
        populateChartTrackerFilter();

        if (isByTrackerMode) {
            loadChartByTracker(period);
        } else {
            loadChartTotal(period);
        }
    }

    function loadChartTotal(period) {
        var tracker = document.getElementById("chart-tracker-filter").value;
        var params = new URLSearchParams();
        if (tracker) params.set("tracker", tracker);
        var url = "/api/uploads/" + period + (params.toString() ? "?" + params.toString() : "");
        var labelKey = period === "daily" ? "day" : period === "weekly" ? "week" : "month";

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

    function loadChartByTracker(period) {
        var url = "/api/uploads/by-tracker/" + period;

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (uploadChart) {
                    uploadChart.destroy();
                }

                var ctx = document.getElementById("upload-chart").getContext("2d");
                uploadChart = new Chart(ctx, {
                    type: "bar",
                    data: {
                        labels: data.labels,
                        datasets: data.datasets,
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: { stacked: true },
                            y: {
                                stacked: true,
                                beginAtZero: true,
                                title: { display: true, text: "GB Uploaded" },
                            },
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    footer: function (items) {
                                        var total = items.reduce(function (sum, item) {
                                            return sum + (item.raw || 0);
                                        }, 0);
                                        return "Total: " + total.toFixed(2) + " GB";
                                    }
                                }
                            }
                        },
                    },
                });
            })
            .catch(function (err) {
                console.error("Chart by tracker load failed:", err);
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

        var tbody = document.getElementById("torrents-body");
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem">Loading...</td></tr>';

        fetch("/api/torrents?" + params.toString())
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderTorrents(data.torrents || []);
                renderPagination(data);
                populateTrackerFilter(data.torrents || []);
            })
            .catch(function (err) {
                console.error("Torrents load failed:", err);
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:red">Failed to load torrents</td></tr>';
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
                    var trackerName = '<a href="#" class="tracker-link" data-tracker="' + escapeHtml(t.tracker_group) + '">' + escapeHtml(t.tracker_group) + '</a>';
                    tr.innerHTML =
                        '<td>' + trackerName + '</td>' +
                        '<td>' + t.torrent_count + '</td>' +
                        '<td>' + (t.uploaded_gb || 0) + ' GB</td>';
                    tbody.appendChild(tr);
                });

                // Bind click handlers for tracker links
                document.querySelectorAll(".tracker-link").forEach(function (link) {
                    link.addEventListener("click", function (e) {
                        e.preventDefault();
                        var tracker = this.dataset.tracker;
                        showTrackerDetails(tracker);
                    });
                });
            })
            .catch(function (err) {
                console.error("Trackers load failed:", err);
            });
    }

    // -----------------------------------------------------------------------
    // Tracker Details Modal
    // -----------------------------------------------------------------------

    var trackerChart = null;

    function showTrackerDetails(trackerGroup) {
        var modal = document.getElementById("tracker-modal");
        modal.classList.add("active");

        document.getElementById("modal-tracker-name").textContent = trackerGroup;
        document.getElementById("tracker-summary-grid").innerHTML = '<p>Loading...</p>';
        document.getElementById("tracker-states-grid").innerHTML = "";
        document.getElementById("tracker-top-torrents-body").innerHTML = "";
        if (trackerChart) { trackerChart.destroy(); trackerChart = null; }

        fetch("/api/tracker-details/" + encodeURIComponent(trackerGroup))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderTrackerDetails(data);
            })
            .catch(function (err) {
                console.error("Tracker details load failed:", err);
                document.getElementById("modal-tracker-name").textContent = "Error";
                document.getElementById("tracker-summary-grid").innerHTML = '<p style="color:red">Failed to load tracker details.</p>';
            });
    }

    function hideTrackerDetails() {
        var modal = document.getElementById("tracker-modal");
        modal.classList.remove("active");
        if (trackerChart) { trackerChart.destroy(); trackerChart = null; }
    }

    document.getElementById("tracker-modal-close").addEventListener("click", hideTrackerDetails);
    document.querySelectorAll("#tracker-modal .modal-overlay")[0].addEventListener("click", hideTrackerDetails);

    function renderTrackerDetails(data) {
        var s = data.summary;

        // Summary grid
        var summaryItems = [
            { label: "Active Torrents", value: s.active_torrents || 0 },
            { label: "Removed Torrents", value: s.removed_torrents || 0 },
            { label: "Library Size", value: (s.active_size_gb || 0) + " GiB" },
            { label: "Total Uploaded", value: (s.total_uploaded_gb || 0) + " GiB" },
            { label: "Total Downloaded", value: (s.total_downloaded_gb || 0) + " GiB" },
            { label: "Earliest Seen", value: s.earliest_seen_str ? fmtDate(s.earliest_seen_str) : "—" },
            { label: "Latest Seen", value: s.latest_seen_str ? fmtDate(s.latest_seen_str) : "—" },
        ];
        document.getElementById("tracker-summary-grid").innerHTML = summaryItems.map(function (item) {
            return '<div class="detail-item">' +
                '<div class="detail-label">' + item.label + '</div>' +
                '<div class="detail-value">' + escapeHtml(String(item.value)) + '</div>' +
                '</div>';
        }).join("");

        // State breakdown
        var states = data.states || [];
        if (states.length > 0) {
            document.getElementById("tracker-states-grid").innerHTML = states.map(function (st) {
                return '<div class="detail-item">' +
                    '<div class="detail-label">' + escapeHtml(st.last_state || "Unknown") + '</div>' +
                    '<div class="detail-value">' + st.count + '</div>' +
                    '</div>';
            }).join("");
        } else {
            document.getElementById("tracker-states-grid").innerHTML = '<p>No active torrents.</p>';
        }

        // Upload history chart
        var history = data.upload_history || [];
        if (history.length > 0) {
            var labels = history.map(function (h) { return fmtDateShort(h.day); });
            var uploaded = history.map(function (h) { return h.uploaded_gb || 0; });

            if (trackerChart) { trackerChart.destroy(); }
            var ctx = document.getElementById("tracker-chart").getContext("2d");
            trackerChart = new Chart(ctx, {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [{
                        label: "Uploaded (GiB)",
                        data: uploaded,
                        borderColor: "rgba(74, 144, 217, 1)",
                        backgroundColor: "rgba(74, 144, 217, 0.1)",
                        fill: true,
                        tension: 0.3,
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: { beginAtZero: true, title: { display: true, text: "GiB" } }
                    }
                }
            });
        }

        // Top torrents table
        var tbody = document.getElementById("tracker-top-torrents-body");
        tbody.innerHTML = "";
        (data.top_torrents || []).forEach(function (t) {
            var tr = document.createElement("tr");
            var nameCell = '<td><a href="#" class="torrent-link" data-hash="' + escapeHtml(t.torrent_hash) + '">' + escapeHtml(t.name) + '</a></td>';
            tr.innerHTML = nameCell +
                '<td>' + (t.size_gb || 0) + '</td>' +
                '<td>' + (t.uploaded_gb || 0) + '</td>' +
                '<td>' + escapeHtml(t.last_state || "—") + '</td>' +
                '<td>' + escapeHtml(t.privacy || "—") + '</td>';
            tbody.appendChild(tr);
        });

        // Bind torrent links inside tracker modal
        document.querySelectorAll("#tracker-top-torrents-body .torrent-link").forEach(function (link) {
            link.addEventListener("click", function (e) {
                e.preventDefault();
                hideTrackerDetails();
                var hash = this.dataset.hash;
                showTorrentDetails(hash);
            });
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

    function formatBytes(bytes) {
        if (!bytes || bytes <= 0) return "—";
        var units = ["B", "KiB", "MiB", "GiB", "TiB"];
        var idx = 0;
        var val = bytes;
        while (val >= 1024 && idx < units.length - 1) {
            val /= 1024;
            idx++;
        }
        return (idx === 0 ? val : val.toFixed(2)) + " " + units[idx];
    }

    // -----------------------------------------------------------------------
    // Analytics — Client-side sorting helpers (Efficiency table only)
    // -----------------------------------------------------------------------

    var efficiencySortCol = "ranking";
    var efficiencySortOrder = "asc";
    var efficiencyData = [];

    function sortTableData(data, sortCol, sortOrder, tableId) {
        var sorted = data.slice().sort(function (a, b) {
            var aVal, bVal;
            // Handle dynamic upload key (e.g., upload_15d_gb) for efficiency table
            if (sortCol === "upload") {
                var uploadKey = Object.keys(a).find(function (k) { return k.startsWith("upload_") && k.endsWith("_gb"); });
                aVal = uploadKey ? a[uploadKey] : 0;
                bVal = uploadKey ? b[uploadKey] : 0;
            }
            // Sorting by classification badge should use the numeric efficiency score
            else if (sortCol === "classification") {
                aVal = a.efficiency || 0;
                bVal = b.efficiency || 0;
            }
            else {
                aVal = a[sortCol];
                bVal = b[sortCol];
            }
            // Handle null/undefined
            if (aVal == null && bVal == null) return 0;
            if (aVal == null) return 1;
            if (bVal == null) return -1;
            // Numeric comparison if both are numbers
            if (typeof aVal === "number" && typeof bVal === "number") {
                return (sortOrder === "asc" ? aVal - bVal : bVal - aVal);
            }
            // String comparison
            var aStr = String(aVal).toLowerCase();
            var bStr = String(bVal).toLowerCase();
            if (aStr < bStr) return sortOrder === "asc" ? -1 : 1;
            if (aStr > bStr) return sortOrder === "asc" ? 1 : -1;
            return 0;
        });
        return sorted;
    }

    function updateSortArrows(tableId, sortCol, sortOrder) {
        document.querySelectorAll("#" + tableId + " thead th[data-sort]").forEach(function (th) {
            var arrow = th.querySelector(".sort-arrow");
            if (arrow) arrow.remove();
            if (th.dataset.sort === sortCol) {
                var span = document.createElement("span");
                span.className = "sort-arrow";
                span.textContent = sortOrder === "asc" ? " \u25B2" : " \u25BC";
                th.appendChild(span);
            }
        });
    }

    // Efficiency sortable headers
    document.querySelectorAll("#efficiency-table thead th[data-sort]").forEach(function (th) {
        th.addEventListener("click", function () {
            var sortCol = th.dataset.sort;
            if (efficiencySortCol === sortCol) {
                efficiencySortOrder = efficiencySortOrder === "asc" ? "desc" : "asc";
            } else {
                efficiencySortCol = sortCol;
                efficiencySortOrder = "asc";
            }
            updateSortArrows("efficiency-table", efficiencySortCol, efficiencySortOrder);
            renderEfficiency(efficiencyData);
        });
        th.style.cursor = "pointer";
    });

    // -----------------------------------------------------------------------
    // Analytics — Top 5 Daily
    // -----------------------------------------------------------------------

    var analyticsTrackerGroupsLoaded = false;

    function populateAnalyticsTrackerFilters() {
        if (analyticsTrackerGroupsLoaded) return;
        analyticsTrackerGroupsLoaded = true;

        fetch("/api/tracker-groups")
            .then(function (r) { return r.json(); })
            .then(function (groups) {
                var selects = [
                    document.getElementById("top5-tracker-filter"),
                    document.getElementById("efficiency-tracker-filter")
                ];
                groups.forEach(function (g) {
                    selects.forEach(function (select) {
                        var opt = document.createElement("option");
                        opt.value = g;
                        opt.textContent = g;
                        select.appendChild(opt);
                    });
                });
            })
            .catch(function (err) {
                console.error("Analytics tracker groups load failed:", err);
            });
    }

    function loadTop5Daily() {
        populateAnalyticsTrackerFilters();

        var tracker = document.getElementById("top5-tracker-filter").value;
        var period = document.getElementById("top5-period-filter").value;
        var limit = document.getElementById("top5-limit-filter").value;
        var params = new URLSearchParams();
        params.set("period", period);
        params.set("limit", limit);
        if (tracker) params.set("tracker", tracker);

        fetch("/api/analytics/top5-daily?" + params.toString())
            .then(function (r) { return r.json(); })
            .then(function (data) {
                renderTop5Daily(data);
            })
            .catch(function (err) {
                console.error("Top Daily load failed:", err);
            });
    }

    function renderTop5Daily(data) {
        var tbody = document.getElementById("top5-daily-body");
        tbody.innerHTML = "";

        data.forEach(function (row) {
            var tr = document.createElement("tr");
            var isTotal = row.name && row.name.endsWith("TOTAL");
            if (isTotal) {
                tr.classList.add("total-row");
            }

            var privacyBadge = "";
            if (row.privacy) {
                var privacyClass = row.privacy === "private" ? "badge-private" : "badge-public";
                privacyBadge = '<span class="badge ' + privacyClass + '">' + escapeHtml(row.privacy) + '</span>';
            }

            var nameCell;
            if (isTotal) {
                nameCell = '<td>' + escapeHtml(row.name || "—") + '</td>';
            } else {
                nameCell = '<td><a class="torrent-name-link" data-hash="' + escapeHtml(row.torrent_hash || "") + '">' + escapeHtml(row.name || "—") + '</a></td>';
            }

            tr.innerHTML =
                '<td>' + escapeHtml(row.day || "—") + '</td>' +
                '<td>' + (row.rank ? "#" + row.rank : "—") + '</td>' +
                nameCell +
                '<td>' + escapeHtml(row.tracker_group || "—") + '</td>' +
                '<td>' + privacyBadge + '</td>' +
                '<td>' + formatBytes(row.uploaded_bytes) + '</td>';

            tbody.appendChild(tr);
        });

        // Bind click handlers on torrent name links
        tbody.querySelectorAll(".torrent-name-link").forEach(function (link) {
            link.addEventListener("click", function () {
                showTorrentDetails(link.dataset.hash);
            });
        });
    }

    // -----------------------------------------------------------------------
    // Analytics — Efficiency
    // -----------------------------------------------------------------------

    function loadEfficiency() {
        populateAnalyticsTrackerFilters();

        var tracker = document.getElementById("efficiency-tracker-filter").value;
        var days = document.getElementById("efficiency-days-filter").value;
        var minSeeding = document.getElementById("efficiency-min-seeding-filter").checked ? 15 : 0;
        var params = new URLSearchParams();
        params.set("days", days);
        params.set("min_seeding_days", minSeeding);
        if (tracker) params.set("tracker", tracker);

        fetch("/api/analytics/efficiency?" + params.toString())
            .then(function (r) { return r.json(); })
            .then(function (data) {
                efficiencyData = data;
                efficiencySortCol = "ranking";
                efficiencySortOrder = "asc";
                updateSortArrows("efficiency-table", efficiencySortCol, efficiencySortOrder);
                renderEfficiency(data);
            })
            .catch(function (err) {
                console.error("Efficiency load failed:", err);
            });
    }

    function renderEfficiency(data) {
        var tbody = document.getElementById("efficiency-body");
        tbody.innerHTML = "";

        // Sort data based on current sort state
        var sorted = sortTableData(data, efficiencySortCol, efficiencySortOrder, "efficiency-table");

        sorted.forEach(function (row) {
            var tr = document.createElement("tr");

            var classification = row.classification || "";
            var badgeClass = "";
            if (classification === "High") badgeClass = "badge-high";
            else if (classification === "Medium") badgeClass = "badge-medium";
            else if (classification === "Low") badgeClass = "badge-low";
            else badgeClass = "badge-very-low";

            var privacyBadge = "";
            if (row.privacy) {
                var privacyClass = row.privacy === "private" ? "badge-private" : "badge-public";
                privacyBadge = '<span class="badge ' + privacyClass + '">' + escapeHtml(row.privacy) + '</span>';
            }

            // Dynamically find the upload column name (e.g., upload_15d_gb)
            var uploadKey = Object.keys(row).find(function (k) { return k.startsWith("upload_") && k.endsWith("_gb"); });
            var uploadVal = uploadKey ? (row[uploadKey] || 0) : 0;

            tr.innerHTML =
                '<td>' + (row.ranking || "—") + '</td>' +
                '<td><a class="torrent-name-link" data-hash="' + escapeHtml(row.torrent_hash || "") + '">' + escapeHtml(row.name || "—") + '</a></td>' +
                '<td>' + (row.size_gb || 0) + '</td>' +
                '<td>' + uploadVal + '</td>' +
                '<td>' + (row.upload_gb_per_seeding_day || 0) + '</td>' +
                '<td>' + (row.efficiency || 0) + '</td>' +
                '<td>' + (row.seeding_days || 0) + '</td>' +
                '<td>' + escapeHtml(row.tracker_group || "—") + '</td>' +
                '<td><span class="badge-efficiency ' + badgeClass + '">' + escapeHtml(classification) + '</span></td>';

            tbody.appendChild(tr);
        });

        // Bind click handlers on torrent name links
        tbody.querySelectorAll(".torrent-name-link").forEach(function (link) {
            link.addEventListener("click", function () {
                showTorrentDetails(link.dataset.hash);
            });
        });
    }

    // Analytics filter change handlers
    document.getElementById("top5-tracker-filter").addEventListener("change", function () {
        loadTop5Daily();
    });
    document.getElementById("top5-limit-filter").addEventListener("change", function () {
        loadTop5Daily();
    });
    document.getElementById("top5-period-filter").addEventListener("change", function () {
        loadTop5Daily();
    });
    document.getElementById("efficiency-tracker-filter").addEventListener("change", function () {
        loadEfficiency();
    });
    document.getElementById("efficiency-days-filter").addEventListener("change", function () {
        loadEfficiency();
    });
    document.getElementById("efficiency-min-seeding-filter").addEventListener("change", function () {
        loadEfficiency();
    });

    // -----------------------------------------------------------------------
    // Initial load — check URL hash after all variables are initialized
    // -----------------------------------------------------------------------

    (function () {
        var hash = location.hash.replace("#", "");
        if (hash && tabLoaders[hash]) {
            switchTab(hash);
        } else {
            switchTab("dashboard");
        }
    })();
})();
