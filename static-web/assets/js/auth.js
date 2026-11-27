/* ===== 致壹 静态站 · 登录态与页面守卫（auth.js）=====
   职责：
   1) 保管令牌（localStorage: edu.token）与当前用户（edu.user）
   2) 每个页面加载时校验身份：未登录 → login.html；角色不符 → 各自的空间
   3) 提供退出登录、修改密码、首次绑定学院/专业/班级的通用弹窗
   注意：真正的数据隔离在后端 middleware（api_server.py），这里只做体验层的拦截。 */
(function () {
  "use strict";

  var BASE = (function () {
    var saved = null;
    try { saved = localStorage.getItem("edu_api_base"); } catch (e) { saved = null; }
    if (saved) return saved;
    var host = location.hostname;
    if (host === "localhost" || host === "127.0.0.1" || host === "") return "http://127.0.0.1:8700/api";
    return location.origin + "/api";
  })();

  var TOKEN_KEY = "edu.token", USER_KEY = "edu.user";
  var file = (location.pathname.split("/").pop() || "index.html").toLowerCase();
  var isLoginPage = file.indexOf("login") === 0;
  var needRole = file.indexOf("student") === 0 ? "student" : "teacher";
  var user = null;

  function token() {
    try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
  }
  function storedUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch (e) { return null; }
  }
  function setSession(t, u) {
    try {
      if (t) localStorage.setItem(TOKEN_KEY, t);
      if (u) localStorage.setItem(USER_KEY, JSON.stringify(u));
    } catch (e) {}
    if (u) user = u;
  }
  function clearSession() {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    } catch (e) {}
    user = null;
  }

  function raw(path, opts) {
    opts = opts || {};
    var headers = {};
    var t = token();
    if (t) headers["Authorization"] = "Bearer " + t;
    var init = { method: opts.method || "GET", headers: headers };
    if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    return fetch(BASE + path, init).then(function (res) {
      return res.text().then(function (txt) {
        var j = null;
        try { j = JSON.parse(txt); } catch (e) {}
        if (!res.ok || (j && j.ok === false)) {
          var err = new Error((j && j.error) || ("HTTP " + res.status));
          err.status = res.status;
          throw err;
        }
        return j && j.data !== undefined ? j.data : j;
      });
    });
  }

  function toast(msg) {
    if (window.Edu && window.Edu.toast) window.Edu.toast(msg);
    else window.alert(msg);
  }

  function loginUrl() {
    var next = (location.pathname.split("/").pop() || "index.html") + location.search + location.hash;
    return "login.html?next=" + encodeURIComponent(next);
  }

  function homeFor(role) {
    return role === "student" ? "student.html" : "index.html";
  }

  function redirectForRoleMismatch(role) {
    // 学生进教师页 → 学生空间；教师进学生页 → 工作台
    location.replace(role === "student" ? "student.html?blocked=1" : "index.html?blocked=1");
  }

  function reveal() {
    document.documentElement.style.visibility = "";
  }

  function guard() {
    if (isLoginPage) { reveal(); return Promise.resolve(null); }
    if (!token()) { location.replace(loginUrl()); return Promise.resolve(null); }
    document.documentElement.style.visibility = "hidden";
    return raw("/auth/me").then(function (u) {
      user = u;
      setSession(token(), u);
      if (u.role !== needRole) { redirectForRoleMismatch(u.role); return null; }
      if (u.role === "student" && u.must_change) {
        // 初始密码未改：页面可见但数据接口被后端拦住，必须先改密
        window.__eduMustChange = true;
        reveal();
        openPassword({ forced: true, onDone: function () {
          window.__eduMustChange = false;
          location.reload();
        } });
        return null;
      }
      reveal();
      document.dispatchEvent(new CustomEvent("edu-auth-ready", { detail: u }));
      return u;
    }).catch(function (e) {
      clearSession();
      if (e && e.status === 403) { redirectForRoleMismatch("student"); return null; }
      location.replace(loginUrl());
      return null;
    });
  }

  function logout() {
    var done = function () { clearSession(); location.replace("login.html"); };
    raw("/auth/logout", { method: "POST" }).then(done, done);
  }

  /* ---------------- 通用弹窗 ---------------- */
  function openModal(title, bodyHtml, footerHtml, opts) {
    opts = opts || {};
    var mask = document.createElement("div");
    mask.className = "modal-mask on";
    mask.innerHTML = '<div class="modal" style="max-width:460px">' +
      '<div class="modal-h"><b>' + title + '</b>' + (opts.closable === false ? "" : '<button class="x" type="button" data-x>×</button>') + '</div>' +
      '<div class="modal-b">' + bodyHtml + '</div>' +
      '<div class="modal-f">' + footerHtml + '</div></div>';
    document.body.appendChild(mask);
    function close() { if (mask.parentNode) mask.parentNode.removeChild(mask); }
    mask.addEventListener("click", function (e) {
      if (opts.closable === false) return;
      if (e.target === mask || e.target.closest("[data-x]")) close();
    });
    return { el: mask, close: close };
  }

  function field(label, id, type, placeholder) {
    return '<div class="field" style="margin-bottom:10px"><label>' + label + '</label>' +
      '<input id="' + id + '" type="' + (type || "text") + '" placeholder="' + (placeholder || "") + '"></div>';
  }

  /* 修改密码：成功后服务端会作废旧会话并返回新令牌 */
  function openPassword(opts) {
    opts = opts || {};
    var forced = !!opts.forced;
    var m = openModal("修改密码",
      (forced ? '<p class="mini" style="margin:0 0 10px">首次登录或密码被重置后，必须先修改初始密码才能进入空间。</p>' : "") +
      field("原密码", "pwdOld", "password") +
      field("新密码（至少 6 位）", "pwdNew", "password") +
      field("确认新密码", "pwdNew2", "password") +
      '<div class="mini" id="pwdMsg"></div>',
      (forced ? "" : '<button class="btn" type="button" data-x>取消</button>') +
      '<button class="btn primary" type="button" data-ok>保存</button>',
      { closable: !forced });
    m.el.addEventListener("click", function (e) {
      if (!e.target.closest("[data-ok]")) return;
      var oldPwd = m.el.querySelector("#pwdOld").value;
      var newPwd = m.el.querySelector("#pwdNew").value;
      var again = m.el.querySelector("#pwdNew2").value;
      var msg = m.el.querySelector("#pwdMsg");
      if (!oldPwd || !newPwd) { msg.textContent = "请填写原密码与新密码"; return; }
      if (newPwd.length < 6) { msg.textContent = "新密码至少 6 位"; return; }
      if (newPwd !== again) { msg.textContent = "两次输入的新密码不一致"; return; }
      raw("/auth/password", { method: "POST", body: { old_password: oldPwd, new_password: newPwd } })
        .then(function (r) {
          if (r && r.token) setSession(r.token, user);
          m.close();
          toast("密码已修改");
          if (typeof opts.onDone === "function") opts.onDone();
        }).catch(function (err) { msg.textContent = err.message || "修改失败"; });
    });
  }

  /* 首次绑定学院/专业/班级（forced=true 时不给关闭入口） */
  function openBind(opts) {
    opts = opts || {};
    var u = user || storedUser() || {};
    var m = openModal("完善学籍信息",
      '<p class="mini" style="margin:0 0 12px">首次登录需绑定学院、专业与班级，绑定后用于匹配你所在班级的课程。</p>' +
      field("学院", "bindCollege", "text", "如：商学院") +
      field("专业", "bindMajor", "text", "如：市场营销") +
      field("班级", "bindClass", "text", "如：移动应用24-1") +
      '<div class="mini" id="bindMsg"></div>',
      (opts.forced ? "" : '<button class="btn" type="button" data-x>稍后</button>') +
      '<button class="btn primary" type="button" data-ok>保存并进入</button>');
    var college = m.el.querySelector("#bindCollege");
    var major = m.el.querySelector("#bindMajor");
    var klass = m.el.querySelector("#bindClass");
    if (u.college) college.value = u.college;
    if (u.major) major.value = u.major;
    if (u.class_name) klass.value = u.class_name;
    m.el.addEventListener("click", function (e) {
      if (!e.target.closest("[data-ok]")) return;
      var msg = m.el.querySelector("#bindMsg");
      var payload = {
        college: college.value.trim(),
        major: major.value.trim(),
        class_name: klass.value.trim()
      };
      if (!payload.college || !payload.major || !payload.class_name) {
        msg.textContent = "学院、专业、班级均为必填";
        return;
      }
      raw("/auth/bind", { method: "POST", body: payload }).then(function (nu) {
        user = nu;
        setSession(token(), nu);
        m.close();
        toast("学籍信息已保存");
        if (typeof opts.onDone === "function") opts.onDone(nu);
        document.dispatchEvent(new CustomEvent("edu-auth-ready", { detail: nu }));
      }).catch(function (err) { msg.textContent = err.message || "保存失败"; });
    });
    return m;
  }

  user = storedUser();
  window.EduAuth = {
    token: token,
    get user() { return user; },
    setSession: setSession,
    clearSession: clearSession,
    guard: guard,
    logout: logout,
    openPassword: openPassword,
    openBind: openBind,
    homeFor: homeFor,
    base: BASE
  };

  // 立即执行守卫（auth.js 在 <head> 中加载，令牌缺失时直接跳转登录页）
  if (!isLoginPage) {
    if (!token()) location.replace(loginUrl());
    else guard();
  }
})();
