#!/usr/bin/env python3
"""Sinh workflow cho kho public (chạy miễn phí trên máy GitHub) từ workflow gốc của kho private.

Chạy:  python tools/public_runner/make_public.py
Kết quả: tools/public_runner/{generate,publish,dispatch}.yml. Sửa workflow gốc thì chạy lại lệnh này rồi dán file vào
.github/workflows/ của kho public. Đừng sửa tay hai nơi.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tools" / "public_runner"
PRIVATE = "phatnh91/dailybreadwithgod"
TOKEN = "${{ secrets.PRIVATE_REPO_TOKEN }}"
WITH = f"        with:\n          repository: {PRIVATE}\n          token: {TOKEN}\n"
RUNS_ON_OLD = "runs-on: ${{ fromJSON(vars.RUNNER_LABELS || '[\"ubuntu-latest\"]') }}"
HEADER = (
    "# KHO PUBLIC: chạy việc trên máy miễn phí của GitHub, lấy mã từ kho private và ghi kết quả về kho private.\n"
    "# Đặt file này ở .github/workflows/{name} của kho public. Cần secret PRIVATE_REPO_TOKEN (Contents: Read and write\n"
    "# trên kho private) và các secret như file gốc. Sinh tự động bằng tools/public_runner/make_public.py: đừng sửa tay.\n"
)


def read(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def sub1(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"Không khớp đúng 1 chỗ ({text.count(old)}): {old[:70]!r}")
    return text.replace(old, new)


def drop_schedule(text: str) -> str:
    """Bỏ khối `schedule:` (lịch GitHub): kho public chạy theo cron-job.org gọi dispatch."""
    return re.sub(r"  schedule:\n(?:(?:    .*|\s*)\n)+?(?=  workflow_dispatch:)", "", text, count=1)


def checkout_private(text: str) -> str:
    """Mọi bước actions/checkout lấy kho private bằng PAT (đăng nhập sẵn nên git push về private chạy được)."""
    text = sub1(text, "      - uses: actions/checkout@v4\n        with:\n          sparse-checkout: tools",
                "      - uses: actions/checkout@v4\n        with:\n          repository: " + PRIVATE + "\n          token: " + TOKEN + "\n          sparse-checkout: tools")
    return text


def generate() -> str:
    t = read("generate.yml")
    t = sub1(t, "name: 1 - Tao video hang ngay", "name: 1 - Tao video (kho public)")
    t = drop_schedule(t)
    t = sub1(t, "permissions:\n  contents: write", "permissions:\n  contents: read")
    t = sub1(t, RUNS_ON_OLD, "runs-on: ubuntu-latest")
    t = checkout_private(t)
    t = sub1(t, "      - uses: actions/checkout@v4\n        if: steps.gate.outputs.run == 'true'\n",
             "      - uses: actions/checkout@v4\n        if: steps.gate.outputs.run == 'true'\n" + WITH)
    t = sub1(t, "          RENDER_LOW_MEM: ${{ contains(vars.RUNNER_LABELS, 'self-hosted') && '1' || '' }}   # chạy trên máy cá nhân: dựng video tiết kiệm RAM\n", "")
    t = sub1(t, "        run: python generate.py\n", """        # Log của kho public ai cũng đọc được: chỉ in dòng trạng thái, không in tên chủ đề hay nội dung kịch bản
        run: |
          set +e
          python generate.py > "$RUNNER_TEMP/gen.log" 2>&1
          rc=$?
          grep -E "Tổng thời lượng|Đã lưu|CẢNH BÁO|vượt giới hạn|AI lỗi|HTTP [0-9]{3}|cấu hình AI|giải mã|AI_CONFIG_SECRET" "$RUNNER_TEMP/gen.log" | cut -c1-200 | head -30
          if [ $rc -ne 0 ]; then echo "Lỗi (mã $rc), 5 dòng cuối:"; tail -n 5 "$RUNNER_TEMP/gen.log" | cut -c1-200; fi
          exit $rc
""")
    t = sub1(t, "          GH_TOKEN: ${{ github.token }}\n        run: bash tools/save_preview.sh",
             "          GH_TOKEN: " + TOKEN + "\n          TARGET_REPO: " + PRIVATE + "\n        run: bash tools/save_preview.sh")
    return HEADER.format(name="generate.yml") + t


def publish() -> str:
    t = read("publish.yml")
    t = sub1(t, "name: 2 - Dang video (Facebook + YouTube)", "name: 2 - Dang video (kho public)")
    t = drop_schedule(t)
    t = sub1(t, "permissions:\n  contents: write\n  actions: read", "permissions:\n  contents: read\n  actions: read")
    t = sub1(t, RUNS_ON_OLD, "runs-on: ubuntu-latest")
    t = checkout_private(t)
    t = sub1(t, "      - uses: actions/checkout@v4\n        if: steps.gate.outputs.run == 'true'\n\n",
             "      - uses: actions/checkout@v4\n        if: steps.gate.outputs.run == 'true'\n" + WITH + "\n")
    # Video đã tạo nằm ở nhánh previews của kho private
    t = sub1(t, "        env:\n          GH_TOKEN: ${{ github.token }}\n        run: |\n          TAG=\"${{ steps.gate.outputs.tag }}\"\n          # Cách chính",
             "        env:\n          GH_TOKEN: " + TOKEN + "\n        run: |\n          TAG=\"${{ steps.gate.outputs.tag }}\"\n          # Cách chính")
    t = sub1(t, "github.com/${GITHUB_REPOSITORY}.git\" /tmp/pvx", "github.com/" + PRIVATE + ".git\" /tmp/pvx")
    # Dự phòng artifact: video không còn nằm ở kho public nên bỏ vòng tìm artifact kho private
    t = re.sub(r"          # Dự phòng: tìm lần chạy gần nhất.*?\n          done\n", "          # (Kho public: không tìm artifact dự phòng, video luôn lấy từ nhánh previews)\n", t, count=1, flags=re.S)
    # Log công khai: chỉ in các dòng trạng thái
    t = sub1(t, "        run: python publish.py\n", """        # Log của kho public ai cũng đọc được: lọc bớt, chỉ giữ dòng trạng thái và lỗi
        run: |
          set +e
          python publish.py > "$RUNNER_TEMP/pub.log" 2>&1
          rc=$?
          grep -E "✅|❌|⚠|Đã đăng|đã đăng|bỏ qua|Bỏ qua|lỗi|Lỗi|HTTP [0-9]{3}|quá hạn|token|Facebook|YouTube|Instagram" "$RUNNER_TEMP/pub.log" | cut -c1-200 | head -40
          if [ $rc -ne 0 ]; then echo "Lỗi (mã $rc), 8 dòng cuối:"; tail -n 8 "$RUNNER_TEMP/pub.log" | cut -c1-200; fi
          exit $rc
""")
    return HEADER.format(name="publish.yml") + t


def dispatch() -> str:
    t = read("dispatch.yml")
    t = sub1(t, "name: 0 - Dieu phoi (goi tu cron-job.org)", "name: 0 - Dieu phoi (kho public, goi tu cron-job.org)")
    t = sub1(t, RUNS_ON_OLD, "runs-on: ubuntu-latest")
    t = checkout_private(t)
    # Chỉ generate.yml và publish.yml có ở kho public: việc khác (podcast, faithfiles) bỏ qua thay vì làm hỏng cả lượt
    t = sub1(t, "gh workflow run $line; }; done", 'gh workflow run $line || echo "(kho public chưa có workflow này, bỏ qua)"; }; done')
    t = sub1(t, 'run() { echo "→ gh workflow run $*"; gh workflow run "$@"; }',
             'run() { echo "→ gh workflow run $*"; gh workflow run "$@" || echo "(kho public chưa có workflow này, bỏ qua)"; }')
    return HEADER.format(name="dispatch.yml") + t


if __name__ == "__main__":
    for name, fn in (("generate.yml", generate), ("publish.yml", publish), ("dispatch.yml", dispatch)):
        (OUT / name).write_text(fn(), encoding="utf-8", newline="\n")
        print("Đã sinh", OUT / name)
