(function () {
  "use strict";

  // -----------------------------------------------------------------
  // Admin Portal. A smaller SPA than officer.js: no petition detail,
  // no sorting of long lists, no voice dictation — just user, role
  // and feature-switch management. The admin signs in through a
  // separate /admin/login page so a review officer never sees an
  // Admin panel link, and administrators have their own landing
  // page distinct from the review workspace.
  //
  // Three admin privileges live under /api/officer/*:
  //   manage_users     — Officers tab (create, edit, delete, reset pw)
  //   manage_roles     — Roles tab (create / edit / delete custom roles)
  //   manage_features  — Features tab (toggle service switches)
  // The SPA hides tabs the signed-in administrator cannot reach.
  // -----------------------------------------------------------------

  const main = document.getElementById("adminMain");
  const account = document.getElementById("account");
  const notice = document.getElementById("notice");

  let user = null;

  function esc(s) {
    return (s == null ? "" : String(s))
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function go(path) {
    history.pushState({}, "", path);
    render();
  }

  function notify(text, kind) {
    notice.className = `notice ${kind || "info"}`;
    notice.textContent = text;
    clearTimeout(notify._t);
    notify._t = setTimeout(() => { notice.textContent = ""; notice.className = ""; }, 4000);
  }

  async function api(path, options) {
    options = options || {};
    options.headers = Object.assign(
      { "Content-Type": "application/json" }, options.headers || {});
    options.credentials = "same-origin";
    const r = await fetch(`/api/officer${path}`, options);
    if (r.status === 204) return null;
    let data = null;
    try { data = await r.json(); } catch (_) {}
    if (!r.ok) {
      const msg = (data && (data.detail || data.message)) || `HTTP ${r.status}`;
      throw new Error(msg);
    }
    return data;
  }

  function has(priv) {
    return !!(user && (user.privileges || []).includes(priv));
  }

  // -------- common dialog shell -------------------------------------

  function dialogShell(title, body) {
    const host = document.getElementById("adminDialog");
    if (!host) return () => {};
    host.innerHTML = `
      <div class="dialog-backdrop" id="dialogBack">
        <div class="dialog" role="dialog" aria-modal="true" aria-label="${esc(title)}">
          <header><h3>${esc(title)}</h3><button class="hbtn ghost small" id="dialogClose" aria-label="Close">×</button></header>
          <div class="dialog-body">${body}</div>
        </div>
      </div>`;
    const close = () => (host.innerHTML = "");
    document.getElementById("dialogClose").onclick = close;
    document.getElementById("dialogBack").onclick = (e) => {
      if (e.target.id === "dialogBack") close();
    };
    return close;
  }

  const USERNAME_RE = /^[a-z0-9][a-z0-9._-]{2,63}$/;
  const ROLE_NAME_RE = /^[a-z0-9][a-z0-9_-]{2,31}$/;

  function bindUsernameValidator(input, errorEl, pattern, hint) {
    const check = () => {
      const v = input.value;
      const ok = pattern.test(v);
      input.setAttribute("aria-invalid", ok || !v ? "false" : "true");
      errorEl.textContent = v && !ok ? hint : "";
      return ok;
    };
    input.addEventListener("input", check);
    return check;
  }

  function roleBadge(role, label) {
    const builtin = role === "admin" || role === "officer";
    const kind = role === "admin" ? "admin" : builtin ? "officer" : "custom";
    const text = label || (role === "admin" ? "Administrator"
                           : role === "officer" ? "Review officer"
                           : role);
    return `<span class="role-badge role-${kind}">${esc(text)}</span>`;
  }

  // -------- header --------------------------------------------------

  function header() {
    if (!user) {
      account.innerHTML = '<a class="hbtn" href="/#home">← Citizen Portal</a>';
      return;
    }
    account.innerHTML =
      `<div class="account-name">${esc(user.name)}` +
      `<small>${esc(user.title || user.role)}</small></div>` +
      '<a class="hbtn ghost" href="/admin" data-go>Dashboard</a>' +
      '<a class="hbtn ghost" href="/admin/account" data-go>My account</a>' +
      '<button class="hbtn" id="logout">Log out</button>';
    document.getElementById("logout").onclick = async () => {
      try { await api("/logout", { method: "POST" }); } catch (_) {}
      user = null;
      go("/admin/login");
    };
  }

  // -------- dashboard ----------------------------------------------

  async function dashboardScreen() {
    // Render the shell immediately so a slow stats call does not
    // stall the whole page — then populate the cards as the data
    // arrives. Fails open: an error on either fetch leaves a dash in
    // the matching metric rather than taking the dashboard down.
    main.innerHTML = `
      <section class="panel admin-home">
        <header class="admin-head">
          <div>
            <p class="eyebrow">ADMIN PORTAL</p>
            <h2>Welcome, ${esc(user.name)}</h2>
            <p class="muted">Signed in as ${roleBadge(user.role, user.title)}. Here is what the service looks like right now.</p>
          </div>
        </header>

        <div class="metrics">
          ${metricTile("officers", "Officers", "The accounts that can sign in")}
          ${metricTile("roles", "Roles", "Built-in plus custom roles")}
          ${metricTile("features", "Features on", "Of the toggleable switches")}
          ${metricTile("sessions", "Active sessions", "Signed-in right now")}
          ${metricTile("logins", "Sign-ins today", "Successful logins since 00:00 UTC")}
          ${metricTile("build", "Build", "The commit this container is on")}
        </div>

        <div class="dashboard-grid">
          <section class="dashboard-col">
            <h3>Quick actions</h3>
            <div class="action-cards">
              ${quickActionCards()}
            </div>
          </section>

          <section class="dashboard-col">
            <h3>Recent activity <small><a href="/admin/activity" data-go>View all →</a></small></h3>
            <div id="recentActivity" class="activity-feed loading">Loading…</div>
          </section>
        </div>
      </section>
      <div id="adminDialog"></div>`;

    try {
      const [stats, health, activity] = await Promise.all([
        api("/stats"),
        fetch("/api/health", { cache: "no-store" }).then((r) => r.ok ? r.json() : null).catch(() => null),
        api("/activity?limit=10").catch(() => ({ entries: [] })),
      ]);
      setMetric("officers",
        `${stats.officers.enabled}`,
        `of ${stats.officers.total} total`);
      setMetric("roles",
        `${stats.roles.total}`,
        `${stats.roles.custom} custom`);
      setMetric("features",
        `${stats.features.enabled}`,
        `of ${stats.features.total}`);
      setMetric("sessions", `${stats.active_sessions}`, "signed in now");
      setMetric("logins", `${stats.logins_today}`, "today");
      if (health && health.build) {
        setMetric("build",
          `<span class="monospace">${esc(String(health.build).slice(0, 7))}</span>`,
          `started ${timeAgo(health.started_at || "")}`);
      }
      renderActivityFeed(
        document.getElementById("recentActivity"),
        (activity.entries || []).slice(0, 8),
        { compact: true });
    } catch (e) {
      notify(e.message || "Could not load the dashboard.", "err");
    }
  }

  function metricTile(key, label, sublabel) {
    return `
      <div class="metric" data-metric="${key}">
        <small>${esc(label)}</small>
        <strong>—</strong>
        <span class="muted small">${esc(sublabel)}</span>
      </div>`;
  }

  function setMetric(key, value, sub) {
    const el = main.querySelector(`[data-metric="${key}"]`);
    if (!el) return;
    el.querySelector("strong").innerHTML = value;
    const sm = el.querySelector(".muted.small");
    if (sm && sub) sm.textContent = sub;
  }

  function quickActionCards() {
    const cards = [];
    if (has("manage_users")) cards.push({
      href: "/admin/users", title: "Officers",
      text: "Add, edit, or remove officer accounts.",
    });
    if (has("manage_roles")) cards.push({
      href: "/admin/roles", title: "Roles",
      text: "Compose roles out of privileges.",
    });
    if (has("manage_features")) cards.push({
      href: "/admin/features", title: "Features",
      text: "Turn parts of the service on and off.",
    });
    if (has("manage_users")) cards.push({
      href: "/admin/sessions", title: "Sessions",
      text: "See who is signed in. Revoke if needed.",
    });
    cards.push({
      href: "/admin/activity", title: "Activity",
      text: "Who did what and when.",
    });
    cards.push({
      href: "/admin/account", title: "My account",
      text: "Change your own password.",
    });
    return cards.map((c) => `
      <a class="admin-card" href="${c.href}" data-go>
        <h4>${esc(c.title)} →</h4>
        <p>${esc(c.text)}</p>
      </a>`).join("");
  }

  // -------- Activity -----------------------------------------------

  async function activityScreen() {
    let entries = [];
    try { entries = (await api("/activity?limit=200")).entries || []; }
    catch (e) { return bodyError(e.message); }
    main.innerHTML = adminShell("Activity",
      `The audit log of administrator actions and sign-ins — newest first.`, `
      <div class="section-head"><div></div>
        <button class="hbtn ghost small" id="activityReload">Reload</button></div>
      <div id="activityFeed" class="activity-feed"></div>`);
    renderActivityFeed(document.getElementById("activityFeed"), entries);
    document.getElementById("activityReload").onclick = activityScreen;
  }

  function renderActivityFeed(host, entries, opts) {
    opts = opts || {};
    if (!host) return;
    if (!entries.length) {
      host.innerHTML = '<p class="muted small">No activity yet.</p>';
      return;
    }
    host.innerHTML = entries.map((e) => {
      const summary = describeAction(e);
      return `
        <div class="activity-row">
          <div class="activity-when">${esc(timeAgo(e.at))}</div>
          <div class="activity-body">
            <strong>${esc(e.actor || "unknown")}</strong>
            ${summary}
            ${opts.compact ? "" : `<div class="activity-at monospace small muted">${esc(e.at)}</div>`}
          </div>
        </div>`;
    }).join("");
  }

  function describeAction(e) {
    const t = (s) => `<code class="pill">${esc(s)}</code>`;
    switch (e.action) {
      case "login": return "signed in";
      case "change_own_password":
        return "changed their own password";
      case "create_user":
        return `created officer ${t(e.target)}${
          e.detail && e.detail.role ? ` with role ${t(e.detail.role)}` : ""}`;
      case "edit_user": {
        const bits = [];
        if (e.detail && e.detail.new_username && e.detail.new_username !== e.target)
          bits.push(`renamed to ${t(e.detail.new_username)}`);
        if (e.detail && e.detail.name) bits.push(`display name → ${t(e.detail.name)}`);
        if (e.detail && e.detail.role) bits.push(`role → ${t(e.detail.role)}`);
        return `edited ${t(e.target)}${bits.length ? ` (${bits.join(", ")})` : ""}`;
      }
      case "reset_password": return `reset password for ${t(e.target)}`;
      case "delete_user": return `deleted officer ${t(e.target)}`;
      case "create_role":
        return `created role ${t(e.target)}`;
      case "edit_role":
        return `edited role ${t(e.target)}`;
      case "delete_role":
        return `deleted role ${t(e.target)}`;
      case "toggle_feature":
        return `turned ${t(e.target)} ${e.detail && e.detail.enabled ? "ON" : "OFF"}`;
      case "revoke_session": return `revoked a session (${t(e.target.slice(0, 10))}…)`;
      case "revoke_all_sessions":
        return `signed ${t(e.target)} out of all sessions (${
          e.detail && e.detail.count ? e.detail.count : 0})`;
      default:
        return `${t(e.action)} on ${t(e.target || "—")}`;
    }
  }

  function timeAgo(when) {
    if (!when) return "";
    const t = Date.parse(when);
    if (!t) return when;
    const s = Math.round((Date.now() - t) / 1000);
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    return `${Math.round(s / 86400)}d ago`;
  }

  // -------- Sessions -----------------------------------------------

  async function sessionsScreen() {
    if (!has("manage_users")) return noAccess();
    let sessions = [];
    try { sessions = (await api("/sessions")).sessions || []; }
    catch (e) { return bodyError(e.message); }
    const rows = sessions.map((s) => `
      <tr>
        <td>${esc(s.name || s.username)}</td>
        <td class="monospace">${esc(s.username)}</td>
        <td>${esc(formatRemaining(s.expires_in_seconds))}</td>
        <td class="row-actions">
          <button class="hbtn ghost small" data-revoke-user="${esc(s.username)}" ${s.username === user.username ? "disabled title='Use Log out to end your own session'" : ""}>Sign out everywhere</button>
          <button class="hbtn danger small" data-revoke-id="${esc(s.id)}" ${s.username === user.username ? "disabled title='Use Log out to end your own session'" : ""}>Revoke</button>
        </td>
      </tr>`).join("");
    main.innerHTML = adminShell("Sessions",
      `Every officer who is signed in right now. Revoke a session to kick a lost laptop; sign-out-everywhere revokes every session that user holds.`, `
      <div class="section-head"><div></div>
        <button class="hbtn ghost small" id="sessionsReload">Reload</button></div>
      <table class="admin-users">
        <thead><tr><th>Name</th><th>Username</th><th>Expires in</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4" class="muted">No active sessions.</td></tr>'}</tbody>
      </table>`);
    document.getElementById("sessionsReload").onclick = sessionsScreen;
    document.querySelectorAll("[data-revoke-id]").forEach((b) => {
      if (b.disabled) return;
      b.onclick = async () => {
        if (!confirm("Revoke this session?")) return;
        try {
          await api(`/sessions/${encodeURIComponent(b.dataset.revokeId)}`,
            { method: "DELETE" });
          notify("Session revoked.", "ok");
          sessionsScreen();
        } catch (e) { notify(e.message, "err"); }
      };
    });
    document.querySelectorAll("[data-revoke-user]").forEach((b) => {
      if (b.disabled) return;
      b.onclick = async () => {
        if (!confirm(`Sign ${b.dataset.revokeUser} out of ALL sessions?`)) return;
        try {
          const r = await api(`/users/${encodeURIComponent(b.dataset.revokeUser)}/revoke`,
            { method: "POST" });
          notify(`Signed out ${(r && r.revoked) || 0} session(s).`, "ok");
          sessionsScreen();
        } catch (e) { notify(e.message, "err"); }
      };
    });
  }

  function formatRemaining(seconds) {
    if (!seconds || seconds < 0) return "expired";
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    const h = Math.floor(seconds / 3600);
    const m = Math.round((seconds % 3600) / 60);
    return m ? `${h}h ${m}m` : `${h}h`;
  }

  // -------- users page ---------------------------------------------

  async function usersScreen() {
    if (!has("manage_users")) return noAccess();
    let users = [];
    try { users = (await api("/users")).users || []; }
    catch (e) { return bodyError(e.message); }
    const rows = users.map((u) => `
      <tr>
        <td>${esc(u.name)}</td>
        <td class="monospace">${esc(u.username)}</td>
        <td>${roleBadge(u.role, u.title)}</td>
        <td class="row-actions">
          <button class="hbtn ghost small" data-edit="${esc(u.username)}">Edit</button>
          <button class="hbtn ghost small" data-pw="${esc(u.username)}">Reset password</button>
          <button class="hbtn danger small" data-del="${esc(u.username)}" ${u.username === user.username ? "disabled title='You cannot delete your own account'" : ""}>Delete</button>
        </td>
      </tr>`).join("");
    main.innerHTML = adminShell("Officers", `
      Add officers, change their roles, reset their passwords. Changes take effect immediately.`, `
      <div class="section-head">
        <div></div>
        <button class="hbtn primary" id="newUser">+ Add officer</button>
      </div>
      <table class="admin-users">
        <thead><tr><th>Name</th><th>Username</th><th>Role</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4" class="muted">No officers yet.</td></tr>'}</tbody>
      </table>`);
    document.getElementById("newUser").onclick = () => showCreateDialog();
    document.querySelectorAll("[data-edit]").forEach((b) => {
      b.onclick = () => showEditDialog(users.find((u) => u.username === b.dataset.edit));
    });
    document.querySelectorAll("[data-pw]").forEach((b) => {
      b.onclick = () => showResetDialog(b.dataset.pw);
    });
    document.querySelectorAll("[data-del]").forEach((b) => {
      if (b.disabled) return;
      b.onclick = async () => {
        const name = b.closest("tr").querySelector("td").textContent;
        if (!confirm(`Delete the "${name}" account? This cannot be undone.`)) return;
        try {
          await api(`/users/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" });
          notify(`Deleted ${name}.`, "ok");
          usersScreen();
        } catch (e) { notify(e.message, "err"); }
      };
    });
  }

  function roleOptions(roles, selected) {
    return roles.map((r) => `
      <option value="${esc(r.name)}" ${r.name === selected ? "selected" : ""}>
        ${esc(r.label)}${r.builtin ? "" : " · " + r.name}
      </option>`).join("");
  }

  async function showCreateDialog() {
    let roles = [];
    try { roles = (await api("/roles")).roles || []; }
    catch (e) { notify(e.message, "err"); return; }
    const close = dialogShell("Add an officer", `
      <form id="createForm" class="form-stack">
        <label>Display name<input id="newName" required maxlength="150" placeholder="e.g. Ravi Kumar"></label>
        <label>Username
          <input id="newUsername" required maxlength="64" placeholder="lowercase, 3–64 chars, letters/digits/._-" autocomplete="off">
          <span class="inline-error" id="newUsernameErr"></span>
        </label>
        <label>Password<input id="newPassword" type="password" required minlength="12" maxlength="256" placeholder="At least 12 characters" autocomplete="new-password"></label>
        <label>Role<select id="newRole">${roleOptions(roles, "officer")}</select></label>
        <p class="error" id="createError" role="alert"></p>
        <div class="dialog-actions">
          <button type="button" class="hbtn ghost" id="createCancel">Cancel</button>
          <button type="submit" class="hbtn primary" id="createSubmit" disabled>Create</button>
        </div>
      </form>`);
    document.getElementById("createCancel").onclick = close;
    const nameInput = document.getElementById("newName");
    const userInput = document.getElementById("newUsername");
    const pwInput = document.getElementById("newPassword");
    const submit = document.getElementById("createSubmit");
    const checkUser = bindUsernameValidator(
      userInput, document.getElementById("newUsernameErr"), USERNAME_RE,
      "Lowercase letters, digits and ._- only. 3–64 characters. Must start with a letter or digit.");
    const refresh = () => {
      submit.disabled = !(nameInput.value.trim() && checkUser() && pwInput.value.length >= 12);
    };
    [nameInput, userInput, pwInput].forEach((el) => el.addEventListener("input", refresh));
    refresh();
    document.getElementById("createForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api("/users", { method: "POST", body: JSON.stringify({
          username: userInput.value, name: nameInput.value,
          password: pwInput.value, role: document.getElementById("newRole").value,
        }) });
        close();
        notify("Officer created.", "ok");
        usersScreen();
      } catch (err) { document.getElementById("createError").textContent = err.message; }
    };
  }

  async function showEditDialog(u) {
    let roles = [];
    try { roles = (await api("/roles")).roles || []; }
    catch (e) { notify(e.message, "err"); return; }
    const isSelf = u.username === user.username;
    const close = dialogShell(`Edit "${u.name}"`, `
      <form id="editForm" class="form-stack">
        <label>Display name<input id="editName" value="${esc(u.name)}" required maxlength="150"></label>
        <label>Username
          <input id="editUsername" value="${esc(u.username)}" required maxlength="64" autocomplete="off">
          <span class="inline-error" id="editUsernameErr"></span>
        </label>
        <label>Role<select id="editRole">${roleOptions(roles, u.role)}</select></label>
        ${isSelf ? '<p class="muted small">Moving your own account to a role without <code>manage_users</code> is refused — you would lose access to this portal. Promote another admin first.</p>' : ""}
        <p class="error" id="editError" role="alert"></p>
        <div class="dialog-actions">
          <button type="button" class="hbtn ghost" id="editCancel">Cancel</button>
          <button type="submit" class="hbtn primary">Save changes</button>
        </div>
      </form>`);
    document.getElementById("editCancel").onclick = close;
    bindUsernameValidator(
      document.getElementById("editUsername"),
      document.getElementById("editUsernameErr"), USERNAME_RE,
      "Lowercase letters, digits and ._- only. 3–64 characters.");
    document.getElementById("editForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api(`/users/${encodeURIComponent(u.username)}`, { method: "PATCH",
          body: JSON.stringify({
            name: document.getElementById("editName").value,
            new_username: document.getElementById("editUsername").value,
            role: document.getElementById("editRole").value,
          }) });
        close();
        notify("Changes saved.", "ok");
        usersScreen();
      } catch (err) { document.getElementById("editError").textContent = err.message; }
    };
  }

  function showResetDialog(username) {
    const close = dialogShell(`Reset password for ${username}`, `
      <form id="resetForm" class="form-stack">
        <p class="muted small">Setting a new password here will sign this user out of every current session.</p>
        <label>New password<input id="resetPw" type="password" required minlength="12" maxlength="256" placeholder="At least 12 characters"></label>
        <p class="error" id="resetError" role="alert"></p>
        <div class="dialog-actions">
          <button type="button" class="hbtn ghost" id="resetCancel">Cancel</button>
          <button type="submit" class="hbtn primary">Reset password</button>
        </div>
      </form>`);
    document.getElementById("resetCancel").onclick = close;
    document.getElementById("resetForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api(`/users/${encodeURIComponent(username)}/password`, { method: "PUT",
          body: JSON.stringify({ new_password: document.getElementById("resetPw").value }) });
        close();
        notify("Password reset.", "ok");
      } catch (err) { document.getElementById("resetError").textContent = err.message; }
    };
  }

  // -------- roles page ---------------------------------------------

  async function rolesScreen() {
    if (!has("manage_roles")) return noAccess();
    let roles = [], privileges = {};
    try {
      [roles, privileges] = await Promise.all([
        api("/roles").then((r) => r.roles || []),
        api("/privileges").then((r) => r.privileges || {}),
      ]);
    } catch (e) { return bodyError(e.message); }
    const rows = roles.map((r) => {
      const privsCell = r.privileges.length
        ? r.privileges.map((p) => `<code class="pill">${esc(p)}</code>`).join(" ")
        : '<span class="muted small">none</span>';
      const builtinLabel = r.builtin ? '<span class="muted small"> (built-in)</span>' : '';
      const memberLabel = r.member_count
        ? `${r.member_count} officer${r.member_count === 1 ? "" : "s"}`
        : '<span class="muted small">no officers</span>';
      const canEdit = !r.builtin, canDelete = !r.builtin && r.member_count === 0;
      return `
        <tr>
          <td><strong>${esc(r.label)}</strong>${builtinLabel}<br><small class="monospace">${esc(r.name)}</small></td>
          <td class="role-privs">${privsCell}</td>
          <td>${memberLabel}</td>
          <td class="row-actions">
            <button class="hbtn ghost small" data-role-edit="${esc(r.name)}" ${canEdit ? "" : "disabled title='Built-in roles cannot be edited'"}>Edit</button>
            <button class="hbtn danger small" data-role-del="${esc(r.name)}" ${canDelete ? "" : (r.builtin ? "disabled title='Built-in roles cannot be deleted'" : "disabled title='Reassign the officers using this role first'")}>Delete</button>
          </td>
        </tr>`;
    }).join("");
    main.innerHTML = adminShell("Roles", `
      Define custom roles with any mix of privileges. Built-in roles (<code>admin</code>, <code>officer</code>) ship with the service and cannot be edited.`, `
      <div class="section-head">
        <div></div>
        <button class="hbtn primary" id="newRole">+ Add role</button>
      </div>
      <table class="admin-users admin-roles">
        <thead><tr><th>Role</th><th>Privileges</th><th>In use</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`);
    document.getElementById("newRole").onclick = () => showCreateRoleDialog(privileges);
    document.querySelectorAll("[data-role-edit]").forEach((b) => {
      if (b.disabled) return;
      b.onclick = () => showEditRoleDialog(roles.find((r) => r.name === b.dataset.roleEdit), privileges);
    });
    document.querySelectorAll("[data-role-del]").forEach((b) => {
      if (b.disabled) return;
      b.onclick = async () => {
        if (!confirm(`Delete the "${b.dataset.roleDel}" role?`)) return;
        try {
          await api(`/roles/${encodeURIComponent(b.dataset.roleDel)}`, { method: "DELETE" });
          notify("Deleted role.", "ok");
          rolesScreen();
        } catch (e) { notify(e.message, "err"); }
      };
    });
  }

  function privilegeCheckboxes(privileges, selected) {
    const set = new Set(selected || []);
    return Object.entries(privileges).map(([name, label]) => `
      <label class="checkbox-row">
        <input type="checkbox" name="priv" value="${esc(name)}" ${set.has(name) ? "checked" : ""}>
        <span><strong>${esc(name)}</strong><br><span class="muted small">${esc(label)}</span></span>
      </label>`).join("");
  }

  function readCheckedPrivileges() {
    return [...document.querySelectorAll('input[name="priv"]:checked')].map((i) => i.value);
  }

  function showCreateRoleDialog(privileges) {
    const close = dialogShell("Add a role", `
      <form id="roleForm" class="form-stack">
        <label>Role name
          <input id="roleName" required maxlength="32" placeholder="lowercase, 3–32 chars, letters/digits/_-" autocomplete="off">
          <span class="inline-error" id="roleNameErr"></span>
        </label>
        <label>Display label<input id="roleLabel" required maxlength="80" placeholder="e.g. Village officer"></label>
        <fieldset class="priv-group"><legend>Privileges</legend>${privilegeCheckboxes(privileges, [])}</fieldset>
        <p class="error" id="roleError" role="alert"></p>
        <div class="dialog-actions">
          <button type="button" class="hbtn ghost" id="roleCancel">Cancel</button>
          <button type="submit" class="hbtn primary" id="roleSubmit" disabled>Create role</button>
        </div>
      </form>`);
    document.getElementById("roleCancel").onclick = close;
    const nameInput = document.getElementById("roleName");
    const labelInput = document.getElementById("roleLabel");
    const submit = document.getElementById("roleSubmit");
    const checkName = bindUsernameValidator(
      nameInput, document.getElementById("roleNameErr"), ROLE_NAME_RE,
      "Lowercase letters, digits, `_` and `-` only. 3–32 characters.");
    const refresh = () => { submit.disabled = !(labelInput.value.trim() && checkName()); };
    [nameInput, labelInput].forEach((el) => el.addEventListener("input", refresh));
    refresh();
    document.getElementById("roleForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api("/roles", { method: "POST", body: JSON.stringify({
          name: nameInput.value, label: labelInput.value,
          privileges: readCheckedPrivileges(),
        }) });
        close();
        notify("Role created.", "ok");
        rolesScreen();
      } catch (err) { document.getElementById("roleError").textContent = err.message; }
    };
  }

  function showEditRoleDialog(role, privileges) {
    const close = dialogShell(`Edit role "${role.label}"`, `
      <form id="roleEditForm" class="form-stack">
        <label>Role name<input value="${esc(role.name)}" disabled></label>
        <label>Display label<input id="roleLabel" value="${esc(role.label)}" required maxlength="80"></label>
        <fieldset class="priv-group"><legend>Privileges</legend>${privilegeCheckboxes(privileges, role.privileges)}</fieldset>
        <p class="error" id="roleEditError" role="alert"></p>
        <div class="dialog-actions">
          <button type="button" class="hbtn ghost" id="roleEditCancel">Cancel</button>
          <button type="submit" class="hbtn primary">Save changes</button>
        </div>
      </form>`);
    document.getElementById("roleEditCancel").onclick = close;
    document.getElementById("roleEditForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api(`/roles/${encodeURIComponent(role.name)}`, { method: "PATCH",
          body: JSON.stringify({
            label: document.getElementById("roleLabel").value,
            privileges: readCheckedPrivileges(),
          }) });
        close();
        notify("Role updated.", "ok");
        rolesScreen();
      } catch (err) { document.getElementById("roleEditError").textContent = err.message; }
    };
  }

  // -------- features page ------------------------------------------

  async function featuresScreen() {
    if (!has("manage_features")) return noAccess();
    let features = [];
    try { features = (await api("/features")).features || []; }
    catch (e) { return bodyError(e.message); }
    const groups = { citizen: [], officer: [], operator: [] };
    features.forEach((f) => (groups[f.audience] = groups[f.audience] || []).push(f));
    const groupHeading = { citizen: "Citizen portal",
                           officer: "Officer portal",
                           operator: "Operator surfaces" };
    const groupBody = (list) => list.map((f) => `
      <div class="feature-row">
        <label class="switch">
          <input type="checkbox" data-flag="${esc(f.name)}" ${f.enabled ? "checked" : ""}>
          <span class="slider"></span>
        </label>
        <div class="feature-text">
          <strong>${esc(f.label)}</strong>
          <small class="monospace">${esc(f.name)}</small>
          <p class="muted small">${esc(f.description)}</p>
        </div>
      </div>`).join("");
    const groupSections = Object.keys(groups)
      .filter((key) => groups[key] && groups[key].length)
      .map((key) => `
        <section class="feature-group">
          <h3>${esc(groupHeading[key] || key)}</h3>
          ${groupBody(groups[key])}
        </section>`).join("");
    main.innerHTML = adminShell("Features", `
      Turn parts of the service on and off. Changes take effect immediately — refresh any open browser to see them.`, groupSections);
    document.querySelectorAll("input[data-flag]").forEach((cb) => {
      cb.onchange = async () => {
        const flag = cb.dataset.flag;
        cb.disabled = true;
        try {
          await api(`/features/${encodeURIComponent(flag)}`, {
            method: "PATCH",
            body: JSON.stringify({ enabled: cb.checked }),
          });
          notify(`${cb.checked ? "Enabled" : "Disabled"} ${flag}.`, "ok");
        } catch (e) {
          notify(e.message, "err");
          cb.checked = !cb.checked;
        } finally { cb.disabled = false; }
      };
    });
  }

  // -------- my account ---------------------------------------------

  function accountScreen() {
    const privs = (user.privileges || []);
    const privsHtml = privs.length
      ? privs.map((p) => `<code class="pill">${esc(p)}</code>`).join(" ")
      : '<span class="muted small">none</span>';
    main.innerHTML = adminShell("My account",
      `Signed in as <strong>${esc(user.name)}</strong> · <span class="monospace">${esc(user.username)}</span>`, `
      <div class="account-grid">
        <section>
          <h3>Role</h3>
          <p>${roleBadge(user.role, user.title)}</p>
          <h3>Privileges</h3>
          <p>${privsHtml}</p>
        </section>
        <section>
          <h3>Change my password</h3>
          <form id="accountForm" class="form-stack">
            <label>Current password<input id="curPw" type="password" required autocomplete="current-password"></label>
            <label>New password<input id="newPw" type="password" required minlength="12" autocomplete="new-password" placeholder="At least 12 characters"></label>
            <label>Confirm new password<input id="confirmPw" type="password" required minlength="12" autocomplete="new-password"></label>
            <p class="error" id="accountError" role="alert"></p>
            <div class="dialog-actions"><button type="submit" class="hbtn primary">Change password</button></div>
          </form>
        </section>
      </div>`);
    document.getElementById("accountForm").onsubmit = async (e) => {
      e.preventDefault();
      const err = document.getElementById("accountError");
      err.textContent = "";
      const newPw = document.getElementById("newPw").value;
      if (newPw !== document.getElementById("confirmPw").value) {
        err.textContent = "The two new-password entries do not match.";
        return;
      }
      try {
        await api("/me/password", { method: "POST", body: JSON.stringify({
          current_password: document.getElementById("curPw").value,
          new_password: newPw,
        }) });
        notify("Password changed. Other sessions have been signed out.", "ok");
        document.getElementById("accountForm").reset();
      } catch (ex) { err.textContent = ex.message; }
    };
  }

  // -------- shell helper -------------------------------------------

  function adminShell(title, intro, body) {
    const tabs = [];
    if (has("manage_users")) tabs.push(["users", "Officers"]);
    if (has("manage_roles")) tabs.push(["roles", "Roles"]);
    if (has("manage_features")) tabs.push(["features", "Features"]);
    if (has("manage_users")) tabs.push(["sessions", "Sessions"]);
    tabs.push(["activity", "Activity"]);
    tabs.push(["account", "My account"]);
    const active = location.pathname.split("/")[2] || "";
    return `
      <section class="panel admin-panel">
        <header class="admin-head">
          <div>
            <p class="eyebrow"><a href="/admin" data-go>ADMIN PORTAL</a> · ${esc(title.toUpperCase())}</p>
            <h2>${esc(title)}</h2>
            <p class="muted">${intro}</p>
          </div>
          <nav class="admin-tabs">
            ${tabs.map(([k, label]) => `
              <a class="hbtn ${active === k ? "primary" : "ghost"}" href="/admin/${k}" data-go>${esc(label)}</a>`).join("")}
          </nav>
        </header>
        <div id="adminBody">${body}</div>
        <div id="adminDialog"></div>
      </section>`;
  }

  function noAccess() {
    main.innerHTML = `
      <section class="panel empty">
        <h2>Not available on your account</h2>
        <p>Your role does not grant the privilege this screen needs. Ask another administrator to grant it, or go back to the <a href="/admin" data-go>dashboard</a>.</p>
      </section>`;
  }

  function bodyError(msg) {
    main.innerHTML = `<section class="panel empty"><h2>Could not load this screen</h2><p class="error" role="alert">${esc(msg)}</p></section>`;
  }

  // -------- router --------------------------------------------------

  async function render() {
    try {
      const path = location.pathname;
      // There is one sign-in surface for the whole portal, and it lives
      // under /officer/login. A bookmark or back-button to /admin/login
      // is handed off cleanly rather than re-rendering a dead screen.
      if (path === "/admin/login" || path === "/admin/login/") {
        location.replace("/officer/login");
        return;
      }
      if (!user) {
        try { user = await api("/me"); }
        catch (_) { location.replace("/officer/login"); return; }
      }
      header();
      if (path === "/admin" || path === "/admin/" || path === "/admin/dashboard")
        return dashboardScreen();
      if (path === "/admin/users") return usersScreen();
      if (path === "/admin/roles") return rolesScreen();
      if (path === "/admin/features") return featuresScreen();
      if (path === "/admin/sessions") return sessionsScreen();
      if (path === "/admin/activity") return activityScreen();
      if (path === "/admin/account") return accountScreen();
      // Fallback: back to dashboard.
      return dashboardScreen();
    } catch (e) {
      bodyError(e.message);
    }
  }

  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-go]");
    if (a && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      go(new URL(a.href).pathname);
    }
  });
  window.addEventListener("popstate", render);
  render();
})();
