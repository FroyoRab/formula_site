from __future__ import annotations

import csv
import html
import re
import urllib.parse
from difflib import SequenceMatcher
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "formulas.csv"
FIELDNAMES = ["id", "name", "content", "created_at"]
HOST = "0.0.0.0"
PORT = 65521
BASE_PATH = "/12sagittarius_ghpishbc"


def app_url(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{BASE_PATH}{normalized}"


def ensure_data_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        with DATA_FILE.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def load_formulas() -> List[Dict[str, str]]:
    ensure_data_file()
    with DATA_FILE.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_formulas(rows: List[Dict[str, str]]) -> None:
    with DATA_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def next_id(rows: List[Dict[str, str]]) -> int:
    return 1 if not rows else max(int(row["id"]) for row in rows) + 1


def create_formula(name: str, content: str) -> str:
    rows = load_formulas()
    new_id = str(next_id(rows))
    rows.append(
        {
            "id": new_id,
            "name": name.strip() or "未命名配方",
            "content": content.strip(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    write_formulas(rows)
    return new_id


def update_formula(formula_id: str, name: str, content: str) -> bool:
    rows = load_formulas()
    updated = False
    for row in rows:
        if row["id"] == formula_id:
            row["name"] = name.strip() or "未命名配方"
            row["content"] = content.strip()
            updated = True
            break
    if updated:
        write_formulas(rows)
    return updated


def delete_formula(formula_id: str) -> bool:
    rows = load_formulas()
    kept_rows = [row for row in rows if row["id"] != formula_id]
    if len(kept_rows) == len(rows):
        return False
    write_formulas(kept_rows)
    return True


def get_formula(formula_id: str) -> Optional[Dict[str, str]]:
    rows = load_formulas()
    for row in rows:
        if row["id"] == formula_id:
            return row
    return None


MAX_SEARCH_LENGTH = 120


def escape_all_characters(text: str) -> str:
    return "".join(f"\\u{ord(ch):04x}" for ch in text)


def sanitize_search_keyword(raw_keyword: str) -> str:
    trimmed = raw_keyword.strip()[:MAX_SEARCH_LENGTH]
    # 对所有字符做安全转义后再参与相似匹配，避免特殊字符影响搜索逻辑。
    return escape_all_characters(trimmed)


def similarity_score(query_escaped: str, name_escaped: str) -> float:
    ratio = SequenceMatcher(None, query_escaped, name_escaped).ratio()
    contains_bonus = 0.15 if query_escaped in name_escaped else 0.0
    return min(1.0, ratio + contains_bonus)


def search_formulas(keyword: str) -> List[Dict[str, str]]:
    rows = load_formulas()[::-1]
    clean_keyword = keyword.strip()[:MAX_SEARCH_LENGTH]
    if not clean_keyword:
        return rows

    query_escaped = sanitize_search_keyword(clean_keyword)
    scored: List[tuple[float, Dict[str, str]]] = []
    for row in rows:
        name_escaped = escape_all_characters(row["name"].lower())
        score = similarity_score(query_escaped.lower(), name_escaped)
        if score >= 0.35:
            scored.append((score, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored]


def excerpt(text: str, limit: int = 70) -> str:
    cleaned = " ".join(text.splitlines())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


def shell_html(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>{html.escape(title)}</title>
  <link rel=\"stylesheet\" href=\"{app_url('/static/style.css')}\">
</head>
<body>
  <div class=\"site\">{body}</div>
</body>
</html>"""


def render_home(keyword: str, rows: List[Dict[str, str]]) -> str:
    items = []
    for row in rows:
        items.append(
            f"""
            <a class=\"formula-row\" href=\"{app_url(f"/formula/{row['id']}")}\">
              <div class=\"formula-main\">
                <h3>{html.escape(row['name'])}</h3>
                <p>{html.escape(excerpt(row['content']))}</p>
              </div>
              <span class=\"time\">{html.escape(row['created_at'])}</span>
            </a>
            """
        )
    if not items:
        items.append('<div class="empty">暂无配方，点击右侧“添加”创建。</div>')

    body = f"""
      <section class=\"home\">
        <form class=\"top-bar\" method=\"get\" action=\"{app_url('/')}\">
          <input type=\"text\" name=\"q\" value=\"{html.escape(keyword)}\" placeholder=\"搜索配方名称\">
          <button class=\"btn primary\" type=\"submit\">搜索</button>
          <a class=\"btn add\" href=\"{app_url('/formula/new')}\">添加</a>
        </form>
        <div class=\"list\">{''.join(items)}</div>
      </section>
    """
    return shell_html("配方首页", body)


def render_detail(formula: Dict[str, str], is_new: bool = False) -> str:
    formula_id = formula.get("id", "new")
    title = "新建配方" if is_new else f"配方详情 #{formula_id}"
    save_action = app_url('/formula/create') if is_new else app_url(f"/formula/{formula_id}/save")
    delete_btn = ""
    if not is_new:
        delete_btn = f"""
        <form method=\"post\" action=\"{app_url(f'/formula/{formula_id}/delete')}\" class=\"inline-form\">
          <button type=\"submit\" class=\"btn danger\">删除</button>
        </form>
        """

    body = f"""
      <section class=\"detail\">
        <header class=\"detail-head\">
          <h2>{html.escape(title)}</h2>
          <a class=\"btn\" href=\"{app_url('/')}\">返回</a>
        </header>

        <div class=\"detail-body\">
          <div class=\"editor\">
            <form method=\"post\" action=\"{save_action}\">
              <label>配方名称</label>
              <input name=\"name\" type=\"text\" value=\"{html.escape(formula.get('name', ''))}\" required>

              <label>配方内容</label>
              <textarea name=\"content\" rows=\"18\" required>{html.escape(formula.get('content', ''))}</textarea>

              <div class=\"actions\">
                <button type=\"submit\" class=\"btn primary\">保存</button>
              </div>
            </form>
            {delete_btn}
          </div>

          <aside class=\"comments\">
            <h3>评论区</h3>
            <div id=\"comment-list\" class=\"comment-list\"></div>
            <form id=\"comment-form\" class=\"comment-form\">
              <input id=\"comment-input\" type=\"text\" placeholder=\"输入评论内容\" required>
              <button type=\"submit\" class=\"btn primary\">提交</button>
            </form>
          </aside>
        </div>
      </section>

      <script>
        (() => {{
          const recipeId = {html.escape(repr(str(formula_id)))};
          const key = `recipe-comments-${{recipeId}}`;
          const listEl = document.getElementById('comment-list');
          const formEl = document.getElementById('comment-form');
          const inputEl = document.getElementById('comment-input');

          function loadComments() {{
            try {{
              return JSON.parse(localStorage.getItem(key) || '[]');
            }} catch (e) {{
              return [];
            }}
          }}

          function saveComments(comments) {{
            localStorage.setItem(key, JSON.stringify(comments));
          }}

          function renderComments() {{
            const comments = loadComments();
            if (!comments.length) {{
              listEl.innerHTML = '<p class="empty">暂无评论</p>';
              return;
            }}
            listEl.innerHTML = comments
              .map(item => `<div class=\"comment-item\"><p>${{item.text}}</p><span>${{item.time}}</span></div>`)
              .join('');
          }}

          formEl.addEventListener('submit', (event) => {{
            event.preventDefault();
            const text = inputEl.value.trim();
            if (!text) return;
            const comments = loadComments();
            comments.push({{
              text,
              time: new Date().toLocaleString('zh-CN')
            }});
            saveComments(comments);
            inputEl.value = '';
            renderComments();
          }});

          renderComments();
        }})();
      </script>
    """
    return shell_html("配方详情", body)


class FormulaHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.redirect(f"{BASE_PATH}/")
            return
        if path in {BASE_PATH, f"{BASE_PATH}/"}:
            query = urllib.parse.parse_qs(parsed.query)
            raw_keyword = query.get("q", [""])[0]
            keyword = raw_keyword.strip()[:MAX_SEARCH_LENGTH]
            self.html_response(render_home(keyword, search_formulas(keyword)))
            return

        if not path.startswith(BASE_PATH):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        app_path = path[len(BASE_PATH):] or "/"
        if app_path == "/static/style.css":
            css = Path("static/style.css").read_text(encoding="utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.end_headers()
            self.wfile.write(css.encode("utf-8"))
            return

        if app_path == "/formula/new":
            self.html_response(render_detail({"name": "", "content": ""}, is_new=True))
            return

        match = re.fullmatch(r"/formula/(\d+)", app_path)
        if match:
            formula = get_formula(match.group(1))
            if not formula:
                self.send_error(HTTPStatus.NOT_FOUND, "Formula not found")
                return
            self.html_response(render_detail(formula))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if not path.startswith(BASE_PATH):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        app_path = path[len(BASE_PATH):] or "/"
        form = self.parse_form_data()
        if form is None:
            return

        if app_path == "/formula/create":
            name = form.get("name", [""])[0]
            content = form.get("content", [""])[0]
            create_formula(name, content)
            self.redirect(app_url("/"))
            return

        save_match = re.fullmatch(r"/formula/(\d+)/save", app_path)
        if save_match:
            formula_id = save_match.group(1)
            name = form.get("name", [""])[0]
            content = form.get("content", [""])[0]
            if not update_formula(formula_id, name, content):
                self.send_error(HTTPStatus.NOT_FOUND, "Formula not found")
                return
            self.redirect(app_url("/"))
            return

        delete_match = re.fullmatch(r"/formula/(\d+)/delete", app_path)
        if delete_match:
            formula_id = delete_match.group(1)
            if not delete_formula(formula_id):
                self.send_error(HTTPStatus.NOT_FOUND, "Formula not found")
                return
            self.redirect(app_url("/"))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def parse_form_data(self) -> Optional[Dict[str, List[str]]]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_data = self.rfile.read(length).decode("utf-8")
            return urllib.parse.parse_qs(raw_data)
        except Exception:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid form data")
            return None

    def html_response(self, content: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()


if __name__ == "__main__":
    ensure_data_file()
    server = ThreadingHTTPServer((HOST, PORT), FormulaHandler)
    print(f"Serving on http://{HOST}:{PORT}{BASE_PATH}/")
    server.serve_forever()
