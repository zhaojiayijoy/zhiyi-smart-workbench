/* ===== 致壹 静态站 · 真实接口客户端 =====
   所有 fetch 走本地 API（默认 http://127.0.0.1:8700/api）。
   接口不可达时各页面回退到 window.EDU 内置演示数据，并提示“演示模式”。 */
(function () {
  "use strict";
  var BASE = (function () {
    var saved = null;
    try { saved = localStorage.getItem("edu_api_base"); } catch (e) { saved = null; }
    if (saved) return saved;
    // 本地预览：静态站跑在 8765，接口在 8700
    var host = location.hostname;
    if (host === "localhost" || host === "127.0.0.1" || host === "") return "http://127.0.0.1:8700/api";
    // 服务器部署：静态站与接口同源（同一个 uvicorn 端口）
    return location.origin + "/api";
  })();

  function _req(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", headers: {} };
    var token = null;
    try { token = localStorage.getItem("edu.token"); } catch (e) { token = null; }
    if (token) init.headers["Authorization"] = "Bearer " + token;
    if (opts.body !== undefined) {
      if (opts.form) {
        init.body = opts.body; // FormData 不要设 Content-Type
      } else {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(opts.body);
      }
    }
    return fetch(BASE + path, init).then(function (res) {
      return res.text().then(function (text) {
        var json = null;
        try { json = JSON.parse(text); } catch (e) {}
        if (!res.ok || (json && json.ok === false)) {
          // 令牌失效：清掉本地登录态（登录页自身不跳转，交给调用方展示错误）
          if (res.status === 401 && path.indexOf("/auth/login") < 0 && window.EduAuth) {
            window.EduAuth.clearSession();
          }
          var e = new Error((json && json.error) || ("HTTP " + res.status));
          e.status = res.status;
          e.code = json && json.code;
          throw e;
        }
        return json && json.data !== undefined ? json.data : json;
      });
    });
  }

  function download(path, filename) {
    var token = null;
    try { token = localStorage.getItem("edu.token"); } catch (e) {}
    return fetch(BASE + path, { headers: token ? { Authorization: "Bearer " + token } : {} }).then(function (res) {
      if (!res.ok) {
        if (res.status === 401 && window.EduAuth) window.EduAuth.clearSession();
        return res.text().then(function (text) {
          var data; try { data = JSON.parse(text); } catch (e) {}
          throw new Error((data && (data.error || data.detail)) || ("下载失败：HTTP " + res.status));
        });
      }
      return res.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url; a.download = filename || "附件";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
    });
  }

  var api = {
    download: download,
    submissions: {
      versions: function (sid) { return _req("/submissions/" + encodeURIComponent(sid) + "/versions"); },
      downloadVersion: function (sid, version, filename) {
        return download("/submissions/" + encodeURIComponent(sid) + "/versions/" + encodeURIComponent(version) + "/file", filename);
      }
    },
    base: BASE,
    health: function () { return _req("/health"); },

    auth: {
      login: function (role, username, password) {
        return _req("/auth/login", { method: "POST", body: { role: role, username: username, password: password } });
      },
      me: function () { return _req("/auth/me"); },
      logout: function () { return _req("/auth/logout", { method: "POST" }); },
      bind: function (p) { return _req("/auth/bind", { method: "POST", body: p }); },
      password: function (oldPwd, newPwd) {
        return _req("/auth/password", { method: "POST", body: { old_password: oldPwd, new_password: newPwd } });
      },
      updateMe: function (p) {
        return _req("/auth/me", { method: "PATCH", body: p });
      }
    },

    courses: {
      list: function (includeArchived) { return _req("/courses" + (includeArchived ? "?include_archived=1" : "")); },
      create: function (p) { return _req("/courses", { method: "POST", body: p }); },
      get: function (id) { return _req("/courses/" + id); },
      overview: function (id) { return _req("/courses/" + id + "/overview"); },
      rounds: function (id) { return _req("/courses/" + id + "/rounds"); },
      archiveRound: function (id, p) { return _req("/courses/" + id + "/rounds/archive", { method: "POST", body: p || {} }); },
      remove: function (id) { return _req("/courses/" + id, { method: "DELETE" }); }
    },
    students: {
      list: function (pid) { return _req("/students?project_id=" + (pid || "")); },
      importFile: function (pid, file) {
        var fd = new FormData();
        fd.append("project_id", pid);
        fd.append("file", file);
        return _req("/students/import", { method: "POST", body: fd, form: true });
      },
      clear: function (pid) { return _req("/students?project_id=" + (pid || ""), { method: "DELETE" }); },
      resetPasswords: function (pid) { return _req("/students/reset-passwords?project_id=" + (pid || ""), { method: "POST" }); }
    },
    student: {
      versions: function (sid) { return _req("/student/submissions/" + encodeURIComponent(sid) + "/versions"); },
      downloadVersion: function (sid, version, filename) {
        return download("/student/submissions/" + encodeURIComponent(sid) + "/versions/" + encodeURIComponent(version) + "/file", filename);
      },
      overview: function (pid) { return _req("/student/overview" + (pid ? "?project_id=" + pid : "")); },
      dashboard: function (pid) { return _req("/student/dashboard" + (pid ? "?project_id=" + pid : "")); },
      wrong: function (pid) { return _req("/student/wrong" + (pid ? "?project_id=" + pid : "")); },
      ask: function (pid, question, kp) {
        return _req("/student/ask", { method: "POST", body: { project_id: pid, question: question, knowledge_point: kp || "" } });
      },
      submit: function (taskId, file, note) {
        var fd = new FormData();
        fd.append("note", note || "");
        if (file) fd.append("file", file);
        return _req("/student/task/" + taskId + "/submit", { method: "POST", body: fd, form: true });
      },
      submissionFileUrl: function (sid) { return BASE + "/student/submissions/" + sid + "/file"; }
    },
    files: {
      list: function (pid) { return _req("/files?project_id=" + (pid || "")); },
      upload: function (o) {
        var fd = new FormData();
        fd.append("project_id", o.projectId);
        fd.append("category", o.category || "资料");
        fd.append("visibility", o.visibility || "both");
        fd.append("file", o.file);
        return _req("/files", { method: "POST", body: fd, form: true });
      },
      text: function (id) { return _req("/files/" + id + "/text"); },
      downloadUrl: function (id) { return BASE + "/files/" + id + "/download"; },
      remove: function (id) { return _req("/files/" + id, { method: "DELETE" }); }
    },
    tasks: {
      list: function (pid, kind) {
        var q = "?project_id=" + (pid || "");
        if (kind) q += "&kind=" + encodeURIComponent(kind);
        return _req("/tasks" + q);
      },
      remove: function (id) { return _req("/tasks/" + id, { method: "DELETE" }); }
    },
    lesson: {
      generate: function (p) { return _req("/lesson/generate", { method: "POST", body: p }); },
      history: function (pid) { return _req("/lesson/history?project_id=" + (pid || "")); },
      get: function (id) { return _req("/lesson/" + id); },
      approve: function (id) { return _req("/lesson/" + id + "/approve", { method: "POST", body: {} }); },
      status: function (id, status, audience) { return _req("/lesson/" + id + "/status", { method: "POST", body: { status: status, audience: audience } }); },
      regenerateAll: function (id) { return _req("/lesson/" + id + "/regenerate-all", { method: "POST", body: {} }); },
      exportUrl: function (id, type) { return BASE + "/lesson/" + id + "/export?type=" + (type || "docx"); }
    },
    outline: {
      get: function (pid) { return _req("/outline?project_id=" + (pid || "")); },
      generate: function (p) { return _req("/outline/generate", { method: "POST", body: p }); },
      save: function (pid, p) { return _req("/outline/" + pid, { method: "PUT", body: p }); },
      revise: function (pid, note) { return _req("/outline/" + pid + "/revise", { method: "POST", body: { teacher_note: note } }); },
      approve: function (pid) { return _req("/outline/" + pid + "/approve", { method: "POST", body: {} }); },
      generateOne: function (pid, no) { return _req("/outline/" + pid + "/sessions/" + no + "/generate", { method: "POST", body: {} }); },
      generateAll: function (pid) { return _req("/outline/" + pid + "/generate-all", { method: "POST", body: {} }); },
      cancelAll: function (pid) { return _req("/outline/" + pid + "/generate-all/cancel", { method: "POST", body: {} }); }
    },
    training: {
      templates: function () { return _req("/training/templates"); },
      generate: function (p) { return _req("/training/generate", { method: "POST", body: p }); },
      history: function (pid) { return _req("/training/history?project_id=" + (pid || "")); },
      get: function (id) { return _req("/training/" + id); },
      status: function (id, status, audience) { return _req("/training/" + id + "/status", { method: "POST", body: { status: status, audience: audience } }); },
      exportUrl: function (id, type) { return BASE + "/training/" + id + "/export?type=" + (type || "docx"); }
    },
    tutor: {
      reply: function (p) { return _req("/tutor/reply", { method: "POST", body: p }); },
      full: function (p) { return _req("/tutor/full", { method: "POST", body: p }); },
      history: function (pid) { return _req("/tutor/history?project_id=" + (pid || "")); },
      status: function (id, st) { return _req("/tutor/records/" + id, { method: "PATCH", body: { status: st } }); }
    },
    review: {
      batch: function (p) { return _req("/review/batch", { method: "POST", body: p }); },
      rubrics: function () { return _req("/review/rubrics"); },
      evaluate: function (p) { return _req("/review/evaluate", { method: "POST", body: p }); },
      history: function (pid) { return _req("/review/history?project_id=" + (pid || "")); },
      get: function (id) { return _req("/review/" + id); },
      patch: function (id, p) { return _req("/review/" + id, { method: "PATCH", body: p }); },
      exportUrl: function (id) { return BASE + "/review/" + id + "/export"; }
    },
    analytics: {
      aggregate: function (p) { return _req("/analytics/aggregate", { method: "POST", body: p }); },
      next: function (p) { return _req("/analytics/next", { method: "POST", body: p }); },
      exportUrl: function (pid) { return BASE + "/analytics/" + pid + "/export"; }
    },
    tools: {
      rubricUrl: function (kind) { return BASE + "/tools/rubric/export?kind=" + (kind || "insight"); },
      gradesUrl: function (pid, className) {
        return BASE + "/tools/grades/export?project_id=" + (pid || "") +
          "&class_name=" + encodeURIComponent(className || "");
      }
    },
    maintenance: {
      backupUrl: function () { return BASE + "/maintenance/backup"; },
      cleanup: function () { return _req("/maintenance/cleanup", { method: "POST", body: {} }); },
      reset: function () { return _req("/maintenance/reset", { method: "POST", body: { confirm: "DELETE" } }); }
    },
    assistant: {
      chat: function (p) { return _req("/assistant/chat", { method: "POST", body: p }); },
      save: function (p) { return _req("/assistant/save", { method: "POST", body: p }); }
    },
    agent: {
      list: function () { return _req("/agent/list"); },
      chat: function (p) { return _req("/agent/chat", { method: "POST", body: p }); }
    },
    settings: {
      get: function () { return _req("/settings"); },
      save: function (p) { return _req("/settings", { method: "POST", body: p }); }
    }
  };

  window.EduAPI = api;
})();
