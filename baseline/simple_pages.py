import html


def esc(value):
    return html.escape(str(value), quote=True)


def page(title, body, status_text=""):
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",Arial,sans-serif;background:#f8fafc;color:#0f172a;}}
.box{{width:min(480px,calc(100vw - 32px));background:#fff;border:1px solid #dbe3ef;border-radius:16px;padding:28px;box-shadow:0 20px 60px rgba(15,23,42,.08);}}
h1{{margin:0 0 12px;font-size:24px;}}
p{{margin:0 0 18px;color:#475569;line-height:1.65;}}
a,.btn{{display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:10px;padding:11px 16px;background:#15945f;color:#fff;text-decoration:none;font-weight:700;}}
.error{{padding:12px 14px;background:#fee2e2;border:1px solid #fca5a5;border-radius:10px;color:#991b1b;margin-bottom:16px;font-weight:700;}}
.muted{{font-size:13px;color:#64748b;margin-top:14px;}}
input{{width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:12px;margin:6px 0 12px;font-size:16px;}}
label{{font-weight:700;color:#334155;}}
</style>
</head>
<body><main class="box">{status_text}{body}</main></body>
</html>"""


def login(error=""):
    err = f'<div class="error">{esc(error)}</div>' if error else ""
    body = f"""
<h1>虚假机场</h1>
<p>请登录后进入管理界面。</p>
{err}
<form method="post" action="/login">
  <label>账号</label>
  <input name="username" required autofocus>
  <label>密码</label>
  <input name="password" type="password" required>
  <button class="btn" style="width:100%;margin-top:4px;" type="submit">登录</button>
</form>
<p class="muted">新版管理界面由前端应用提供，旧服务端页面已移除。</p>
"""
    return page("登录", body)


def forbidden():
    body = """
<h1>权限不足</h1>
<p>当前账号没有访问该操作的权限。</p>
<a href="/links">返回</a>
"""
    return page("权限不足", body)


def not_found():
    body = """
<h1>页面不存在</h1>
<p>旧服务端页面已移除，请返回新版面板。</p>
<a href="/">返回面板</a>
"""
    return page("页面不存在", body)


def qr_error(message):
    body = f"""
<h1>二维码生成失败</h1>
<p>{esc(message)}</p>
<a href="/links">返回节点页面</a>
"""
    return page("二维码生成失败", body)
