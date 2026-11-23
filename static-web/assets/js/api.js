/* ===== 致壹 静态站 · 真实接口客户端 =====
   所有 fetch 走本地 API（默认 http://127.0.0.1:8700/api）。
   接口不可达时各页面回退到 window.EDU 内置演示数据，并提示“演示模式”。 */
(function () {
  "use strict";
  var BASE = (function () {
    try { return localStorage.getItem("edu_api_base") || "http://127.0.0.1:8700/api"; }
    catch (e) { return "http://127.0.0.1:8700/api"; }
  })();

  function _req(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", headers: {} };
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
          throw new Error((json && json.error) || ("HTTP " + res.status));
        }
        return json && json.data !== undefined ? json.data : json;
      });
    });
  }

  var api = {
    base: BASE,
    health: function () { return _req("/health"); },

    courses: {
      list: function () { return _req("/courses"); },
      create: function (p) { return _req("/courses", { method: "POST", body: p }); },
      get: function (id) { return _req("/courses/" + id); },
      overview: function (id) { return _req("/courses/" + id + "/overview"); },
      remove: function (id) { return _req("/courses/" + id, { method: "DELETE" }); }
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
      exportUrl: function (id, type) { return BASE + "/lesson/" + id + "/export?type=" + (type || "docx"); }
    },
    training: {
      generate: function (p) { return _req("/training/generate", { method: "POST", body: p }); },
      history: function (pid) { return _req("/training/history?project_id=" + (pid || "")); },
      get: function (id) { return _req("/training/" + id); },
      exportUrl: function (id, type) { return BASE + "/training/" + id + "/export?type=" + (type || "docx"); }
    },
    tutor: {
      reply: function (p) { return _req("/tutor/reply", { method: "POST", body: p }); },
      full: function (p) { return _req("/tutor/full", { method: "POST", body: p }); },
      history: function (pid) { return _req("/tutor/history?project_id=" + (pid || "")); }
    },
    review: {
      evaluate: function (p) { return _req("/review/evaluate", { method: "POST", body: p }); },
      history: function (pid) { return _req("/review/history?project_id=" + (pid || "")); },
      get: function (id) { return _req("/review/" + id); },
      exportUrl: function (id) { return BASE + "/review/" + id + "/export"; }
    },
    analytics: {
      aggregate: function (p) { return _req("/analytics/aggregate", { method: "POST", body: p }); },
      next: function (p) { return _req("/analytics/next", { method: "POST", body: p }); },
      exportUrl: function (pid) { return BASE + "/analytics/" + pid + "/export"; }
    },
    assistant: {
      chat: function (p) { return _req("/assistant/chat", { method: "POST", body: p }); }
    },
    settings: {
      get: function () { return _req("/settings"); },
      save: function (p) { return _req("/settings", { method: "POST", body: p }); }
    },
    student: {
      dashboard: function (pid, student) {
        return _req("/student/dashboard?project_id=" + (pid || "") + "&student=" + encodeURIComponent(student || ""));
      }
    }
  };

  window.EduAPI = api;
})();
