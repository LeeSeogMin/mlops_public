#!/usr/bin/env python3
"""한국어 마크다운 원고를 PDF로 바꾼다.

변환 경로:
    마크다운 --(pandoc)--> 자체완결 HTML(이미지 base64 내장) --(Chromium)--> PDF

LaTeX(xelatex)나 wkhtmltopdf를 설치하지 않아도 되고, 표와 그림이 브라우저에서
보이던 모양 그대로 나온다. 한글 폰트는 시스템 폰트(맑은 고딕 등)를 쓴다.

PDF 출력 엔진은 두 가지다.
    chrome     설치된 Chrome/Edge를 headless로 불러 --print-to-pdf로 인쇄한다.
               추가 설치가 필요 없어 기본값이다. 쪽 번호를 넣지 못한다.
    playwright playwright의 격리 Chromium을 부른다. 쪽 번호를 넣을 수 있고,
               사용자의 브라우저 프로필과 무관하다. `pip install playwright`와
               `playwright install chromium`이 필요하다.

두 엔진 모두 Chromium 계열이지만 버전이 달라 줄바꿈 위치가 한두 줄 어긋날 수
있다. 같은 문서를 여러 번 낼 때는 엔진을 고정한다.

사용법:
    python md2pdf.py docs/ch4.md
    python md2pdf.py docs/ch4.md --out output/pdf/ch4.pdf
    python md2pdf.py docs/ch1.md docs/ch2.md --outdir output/pdf
    python md2pdf.py 강의계획서.md --page-numbers      # playwright 필요
    python md2pdf.py docs/ch4.md --css my-style.css --keep-html
"""

from __future__ import annotations

import argparse
import html as html_mod
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# korean-md-pdf 스킬의 md2pdf.py를 저장소에 옮겨 둔 것이다. 스킬이 없는 기계에서도
# 같은 결과가 나오도록 스타일시트도 scripts/md2pdf.css로 함께 옮겼다.
# 직접 부르지 않고 scripts/md2pdf.py(생성 기록을 남기는 래퍼)를 거친다.
DEFAULT_CSS = Path(__file__).resolve().parent / "md2pdf.css"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]

# pandoc 입력 확장.
#   gfm                  표·체크박스 등 깃허브 마크다운 문법
#   footnotes            [^1] 각주
#   yaml_metadata_block  프론트매터를 본문에 찍지 않고 메타데이터로 처리
#   tex_math_dollars     달러 기호 수식을 인식(--mathjax와 함께 쓸 때만 의미가 있다)
PANDOC_FROM = "gfm+footnotes+yaml_metadata_block+tex_math_dollars"

# ```mermaid 펜스 블록. 여는 펜스부터 닫는 펜스까지를 통째로 잡는다.
MERMAID_FENCE_RE = re.compile(r"^```\s*mermaid\s*\n(.*?)^```\s*$",
                              re.MULTILINE | re.DOTALL)

# 공문 기호(□/○/– 등)로 시작하는 줄. □/○/– 계층 원고에서 줄머리 공백은
# 들여쓰기인데, HTML은 연속 공백을 접으므로 pandoc을 거치면 사라진다.
# 이런 줄을 내어쓰기 div(.h0/.h1/.h2 — default.css)로 감싸, 들여쓰기와
# 줄넘김 정렬(hanging indent)을 함께 보존한다.
# 마크다운 목록 기호(-, *, 숫자.)는 건드리지 않는다 — 그쪽은 pandoc이
# 목록 구조로 들여쓰기를 처리한다.
INDENT_MARK_RE = re.compile(r"^( *)([□■●○◦▪–—])(?=\s|$)")

# mermaid.js를 CDN에서 받아 <pre class="mermaid">를 인라인 SVG(벡터)로 그린다.
# PNG가 아니라 SVG이므로 어느 배율에서도 선명하다. 인터넷 연결이 필요하며,
# CDN 접속에 실패하면 다이어그램 자리는 mermaid 소스 텍스트로 남는다.
MERMAID_SNIPPET = """<style>
pre.mermaid { text-align: center; page-break-inside: avoid;
              background: none; border: none; padding: 0; }
pre.mermaid svg { max-width: 100%; height: auto; }
</style>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
try {
  mermaid.initialize({
    startOnLoad: false,
    theme: "neutral",
    fontFamily: "'Malgun Gothic','Apple SD Gothic Neo',sans-serif",
  });
  await mermaid.run();
} finally {
  window.__mermaidDone = true;   // 실패해도 인쇄 대기가 풀리도록 항상 세운다.
}
</script>"""

FOOTER_TEMPLATE = (
    '<div style="width:100%;font-size:8pt;color:#666;'
    "font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;"
    'text-align:center;padding:0 16mm;">'
    '<span class="pageNumber"></span> / <span class="totalPages"></span>'
    "</div>"
)


def find_chrome() -> str:
    """설치된 Chrome 또는 Edge의 실행 파일 경로를 찾는다."""
    for name in ("chrome", "google-chrome", "chromium", "chromium-browser", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "Chrome 또는 Edge를 찾지 못했습니다. PDF 변환에는 둘 중 하나가 필요합니다.\n"
        "Playwright가 설치되어 있다면 --engine playwright를 쓰십시오."
    )


def require_pandoc() -> str:
    """pandoc 실행 파일 경로를 확인한다. 없으면 설치 방법을 알린다."""
    found = shutil.which("pandoc")
    if not found:
        raise FileNotFoundError(
            "pandoc을 찾지 못했습니다. https://pandoc.org 에서 설치하십시오.\n"
            "  Windows: winget install --id JohnMacFarlane.Pandoc\n"
            "  macOS:   brew install pandoc"
        )
    return found


def preserve_indent(text: str) -> tuple[str, int]:
    """공문 기호(□/○/– 등) 줄을 내어쓰기 div로 감싼다.

    div와 내용 사이에 빈 줄을 두면 pandoc(gfm)이 내용을 일반 문단으로
    해석하므로 굵게·코드 같은 인라인 마크다운이 살아 있고, 브라우저는
    그 문단을 div 안에 넣어 준다. 들여쓰기 단계는 줄머리 공백 수로 정한다
    (0칸 = h0, 1~2칸 = h1, 3칸 이상 = h2). 스타일은 default.css의 .h0/.h1/.h2.

    펜스 코드 블록(``` 또는 ~~~) 안은 건드리지 않는다 — 코드의 들여쓰기는
    <pre>가 그대로 보존하기 때문이며, 잘못 바꾸면 코드가 달라진다.
    반환값: (바뀐 텍스트, 감싼 줄 수)
    """
    out: list[str] = []
    in_fence = False
    changed = 0
    for line in text.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        m = INDENT_MARK_RE.match(line)
        if not m:
            out.append(line)
            continue
        n = len(m.group(1))
        level = 0 if n == 0 else (1 if n <= 2 else 2)
        # </div> 뒤에 빈 줄을 하나 둔다. 이것이 없으면 pandoc(gfm)이 닫는 태그부터
        # 다음 빈 줄까지를 하나의 원시 HTML 블록으로 묶어, 뒤따르는 목록 줄의
        # 굵게·코드 같은 인라인 마크다운이 변환되지 않고 원문 그대로 나간다.
        out += [f'<div class="h{level}">', "", line.strip(), "", "</div>", ""]
        changed += 1
    return "\n".join(out), changed


def preprocess_markdown(md_path: Path) -> tuple[Path, bool, int, int]:
    """pandoc에 넣기 전 원문을 손질한 임시 마크다운을 만든다.

    1) 공문 기호 줄의 들여쓰기 보존(preserve_indent)
    2) ```mermaid 펜스를 <pre class="mermaid"> 원시 HTML로 교체 — pandoc은
       mermaid를 일반 코드 블록으로 취급해 소스 텍스트가 그대로 찍히므로,
       mermaid.js가 인식하는 형태로 바꿔 둔다. 내용은 HTML 이스케이프해 두며,
       mermaid.js는 textContent를 읽으므로 원문이 보존된다.
    반환값: (pandoc에 넘길 경로, 임시 파일 여부, mermaid 블록 수, 들여쓰기 줄 수)
    """
    text = md_path.read_text(encoding="utf-8")
    text, n_indent = preserve_indent(text)
    n_mermaid = 0

    def repl(match: re.Match) -> str:
        nonlocal n_mermaid
        n_mermaid += 1
        return '<pre class="mermaid">\n' + html_mod.escape(match.group(1)) + "</pre>"

    text = MERMAID_FENCE_RE.sub(repl, text)
    if n_mermaid == 0 and n_indent == 0:
        return md_path, False, 0, 0
    tmp_path = md_path.with_suffix(".mermaid.tmp.md")
    tmp_path.write_text(text, encoding="utf-8")
    return tmp_path, True, n_mermaid, n_indent


def inject_mermaid(html_path: Path) -> None:
    """pandoc이 만든 HTML의 </body> 앞에 mermaid.js 로더를 넣는다."""
    html_text = html_path.read_text(encoding="utf-8")
    html_text = html_text.replace("</body>", MERMAID_SNIPPET + "\n</body>", 1)
    html_path.write_text(html_text, encoding="utf-8")


def md_to_html(md_path: Path, html_path: Path, css_path: Path,
               mathjax: bool, resource_roots: list[Path]) -> None:
    """pandoc으로 마크다운을 이미지가 내장된 단일 HTML로 바꾼다.

    --embed-resources로 그림을 base64로 넣기 때문에 HTML 하나만 있으면
    렌더링이 끝난다. 브라우저가 파일 경로를 못 찾아 그림이 빠지는 일이 없다.
    """
    resource_path = os.pathsep.join(str(p) for p in resource_roots)
    cmd = [
        require_pandoc(),
        str(md_path),
        "--from", PANDOC_FROM,
        "--to", "html5",
        "--standalone",
        "--embed-resources",
        "--css", str(css_path),
        "--resource-path", resource_path,
        "--metadata", f"title={md_path.stem}",
        "--output", str(html_path),
    ]
    if mathjax:
        # MathJax는 CDN에서 내려받는다. 오프라인에서는 수식이 원문 그대로 남는다.
        cmd.append("--mathjax")
    subprocess.run(cmd, check=True)


def html_to_pdf_chrome(html_path: Path, pdf_path: Path, attempts: int = 2) -> None:
    """설치된 Chrome/Edge를 headless로 불러 HTML을 인쇄한다.

    Chrome CLI는 인쇄를 끝내지 못한 경우에도 종료 코드 0을 낸다. 그래서 성공
    판정은 종료 코드가 아니라 PDF 파일이 실제로 생겼는지로 한다. 프로세스가
    처음 뜰 때(콜드 스타트) 렌더링이 --virtual-time-budget 안에 끝나지 않아
    빈손으로 종료하는 경우가 있으므로, 파일이 없으면 예산을 늘려 한 번 더 부른다.
    """
    chrome = find_chrome()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    result = None

    for attempt in range(1, attempts + 1):
        # 재시도할 때는 렌더링 대기 예산을 두 배로 준다.
        budget = 15000 * attempt
        with tempfile.TemporaryDirectory() as profile_dir:
            cmd = [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                # 브라우저가 붙이는 파일 경로·날짜 머리말을 끈다.
                "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw",
                # 폰트·이미지 렌더링이 끝나기 전에 인쇄되는 것을 막는다.
                f"--virtual-time-budget={budget}",
                f"--user-data-dir={profile_dir}",
                f"--print-to-pdf={pdf_path}",
                html_path.resolve().as_uri(),
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True,
                                        timeout=180)
            except subprocess.TimeoutExpired:
                result = None

        if pdf_path.exists():
            if attempt > 1:
                print(f"        (Chrome 재시도 {attempt}회째에 성공)")
            return
        if attempt < attempts:
            print(f"        (PDF가 나오지 않아 재시도합니다 {attempt}/{attempts - 1})")

    if result is not None:
        sys.stderr.write((result.stdout or "") + "\n" + (result.stderr or "") + "\n")
    raise RuntimeError(
        f"PDF가 만들어지지 않았습니다: {pdf_path}\n"
        "Chrome 인쇄가 계속 실패하면 --engine playwright를 쓰십시오."
    )


def html_to_pdf_playwright(html_path: Path, pdf_path: Path, page_numbers: bool,
                           wait_mermaid: bool = False) -> None:
    """playwright의 격리 Chromium으로 인쇄한다. 쪽 번호를 넣을 수 있다."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright가 설치되어 있지 않습니다.\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from exc

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    # 머리말·꼬리말을 켜면 CSS의 @page 여백이 무시되므로 여기서 직접 준다.
    margin = {"top": "18mm", "right": "16mm", "bottom": "20mm", "left": "16mm"}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri())
        if wait_mermaid:
            # mermaid.js가 SVG 렌더링을 끝낼 때까지 기다린 뒤 인쇄한다.
            page.wait_for_function("window.__mermaidDone === true", timeout=60000)
        page.emulate_media(media="print")
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin=margin,
            display_header_footer=page_numbers,
            header_template="<div></div>" if page_numbers else None,
            footer_template=FOOTER_TEMPLATE if page_numbers else None,
        )
        browser.close()

    if not pdf_path.exists():
        raise RuntimeError(f"PDF가 만들어지지 않았습니다: {pdf_path}")


def resolve_engine(requested: str, page_numbers: bool) -> str:
    """엔진 이름을 확정한다. auto는 쪽 번호 요구 여부로 갈린다."""
    if requested != "auto":
        if requested == "chrome" and page_numbers:
            raise ValueError(
                "chrome 엔진은 쪽 번호를 넣지 못합니다. "
                "--engine playwright를 쓰거나 --page-numbers를 빼십시오."
            )
        return requested
    return "playwright" if page_numbers else "chrome"


def convert_one(md_path: Path, pdf_path: Path, css_path: Path,
                engine: str, page_numbers: bool, mathjax: bool,
                keep_html: bool, project_root: Path) -> Path:
    """마크다운 한 건을 PDF로 바꾼다. 중간 HTML은 기본적으로 지운다."""
    html_path = md_path.with_suffix(".md.html")
    resource_roots = [md_path.parent, project_root]
    src_md, is_tmp, n_mermaid, n_indent = preprocess_markdown(md_path)
    try:
        note = (f", mermaid {n_mermaid}개" if n_mermaid else "") + \
               (f", 들여쓰기 보존 {n_indent}줄" if n_indent else "")
        print(f"  [1/2] 마크다운 -> HTML  ({html_path.name}{note})")
        md_to_html(src_md, html_path, css_path, mathjax, resource_roots)
        if n_mermaid:
            inject_mermaid(html_path)

        # chrome CLI의 --virtual-time-budget 인쇄는 mermaid의 비동기 렌더링을
        # 끝까지 기다리지 못해 일부 다이어그램이 빈칸으로 남는다(첫 블록만
        # 성공하는 사례 확인됨). mermaid가 있으면 playwright로 전환한다.
        if n_mermaid and engine == "chrome":
            try:
                import playwright  # noqa: F401
                engine = "playwright"
                print("        (mermaid 렌더링 대기를 위해 playwright 엔진으로 전환)")
            except ImportError:
                print("        경고: mermaid 문서는 playwright 엔진을 권장합니다. "
                      "chrome 엔진에서는 일부 다이어그램이 빈칸으로 남을 수 있습니다.")

        print(f"  [2/2] HTML -> PDF       ({pdf_path.name}, engine={engine})")
        if engine == "playwright":
            html_to_pdf_playwright(html_path, pdf_path, page_numbers,
                                   wait_mermaid=bool(n_mermaid))
        else:
            html_to_pdf_chrome(html_path, pdf_path)
    finally:
        if is_tmp:
            src_md.unlink(missing_ok=True)
        if not keep_html:
            html_path.unlink(missing_ok=True)
    return pdf_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="한국어 마크다운 -> PDF 변환 (pandoc + Chromium)")
    parser.add_argument("markdown", nargs="+",
                        help="변환할 마크다운 파일. 여러 개를 줄 수 있다")
    parser.add_argument("--out", default=None,
                        help="저장할 PDF 경로. 입력이 파일 하나일 때만 쓴다")
    parser.add_argument("--outdir", default=None,
                        help="PDF를 모아 둘 폴더. 파일명은 입력과 같게 둔다")
    parser.add_argument("--css", default=None,
                        help=f"스타일시트 경로. 기본값: {DEFAULT_CSS}")
    parser.add_argument("--engine", choices=["auto", "chrome", "playwright"],
                        default="auto", help="PDF 출력 엔진 (기본 auto)")
    parser.add_argument("--page-numbers", action="store_true",
                        help="쪽 번호를 아래쪽 가운데에 넣는다 (playwright 필요)")
    parser.add_argument("--mathjax", action="store_true",
                        help="달러 기호 수식을 MathJax로 렌더링한다 (인터넷 연결 필요)")
    parser.add_argument("--keep-html", action="store_true",
                        help="중간 HTML 파일을 지우지 않는다")
    parser.add_argument("--project-root", default=None,
                        help="그림 상대 경로의 기준 폴더. 기본은 현재 작업 폴더")
    args = parser.parse_args()

    md_paths = [Path(m).resolve() for m in args.markdown]
    missing = [p for p in md_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"파일을 찾을 수 없습니다: {p}")
        return 1

    if args.out and len(md_paths) > 1:
        print("--out은 입력이 파일 하나일 때만 쓸 수 있습니다. --outdir을 쓰십시오.")
        return 1

    css_path = Path(args.css).resolve() if args.css else DEFAULT_CSS
    if not css_path.exists():
        print(f"스타일시트를 찾을 수 없습니다: {css_path}")
        return 1

    project_root = Path(args.project_root).resolve() if args.project_root else Path.cwd()

    try:
        engine = resolve_engine(args.engine, args.page_numbers)
    except ValueError as exc:
        print(exc)
        return 1

    outdir = Path(args.outdir).resolve() if args.outdir else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    made: list[Path] = []
    for idx, md_path in enumerate(md_paths, start=1):
        if args.out:
            pdf_path = Path(args.out).resolve()
        elif outdir:
            pdf_path = outdir / (md_path.stem + ".pdf")
        else:
            pdf_path = md_path.with_suffix(".pdf")

        print(f"[{idx}/{len(md_paths)}] {md_path.name}")
        try:
            convert_one(md_path, pdf_path, css_path, engine,
                        args.page_numbers, args.mathjax, args.keep_html,
                        project_root)
        except (RuntimeError, FileNotFoundError, subprocess.CalledProcessError) as exc:
            print(f"  실패: {exc}")
            return 1
        made.append(pdf_path)

    print()
    for pdf_path in made:
        size_kb = pdf_path.stat().st_size / 1024
        print(f"완료: {pdf_path} ({size_kb:,.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
