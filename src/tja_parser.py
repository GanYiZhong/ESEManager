"""
TJA 檔案解析工具
用於從 TJA 譜面檔案中提取歌曲資訊
"""

import os
import re
from pathlib import Path
from typing import Dict, Optional


# COURSE 標記 → 五大難度鍵（數字或英文/日文皆可）
COURSE_MAP = {
    "0": "easy", "easy": "easy", "kantan": "easy",
    "1": "normal", "normal": "normal", "futsuu": "normal", "futsu": "normal",
    "2": "hard", "hard": "hard", "muzukashii": "hard",
    "3": "oni", "oni": "oni",
    "4": "ura", "edit": "ura", "ura": "ura", "ura oni": "ura", "uraoni": "ura",
}
DIFFICULTIES = ["easy", "normal", "hard", "oni", "ura"]


class TJAParser:
    """TJA 檔案解析器"""

    def __init__(self):
        """初始化解析器"""
        # TJA 檔案中的 metadata 欄位
        self.metadata_fields = [
            'TITLE',
            'TITLEJA',
            'SUBTITLE',
            'SUBTITLEJA',
            'BPM',
            'WAVE',
            'OFFSET',
            'DEMOSTART',
            'GENRE',
            'SCOREMODE',
            'MAKER'
        ]

    @staticmethod
    def decode_bytes(data: bytes) -> Optional[str]:
        """嘗試多種編碼把 .tja 的 bytes 解碼成文字（TJA 常見 utf-8 或 shift-jis）。"""
        for enc in ('utf-8-sig', 'utf-8', 'shift-jis', 'cp932', 'latin-1'):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return None

    def parse_text(self, content: str) -> Dict[str, str]:
        """從 TJA 文字內容解析 metadata（不含檔案路徑欄位）。"""
        metadata = {}
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('//'):
                continue
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    field = parts[0].strip().upper()
                    value = parts[1].strip()
                    if field in [f.upper() for f in self.metadata_fields]:
                        metadata[field.lower()] = value
            # 遇到譜面開始標記就停止（後面是譜面資料）
            if line.startswith('#START') or line.startswith('COURSE:'):
                break
        return metadata

    def parse_courses(self, content: str) -> Dict[str, Optional[int]]:
        """掃描整份 TJA，取出五大難度（easy/normal/hard/oni/ura）的等級數。

        TJA 以 COURSE: 切分每個難度區塊，各區塊內的 LEVEL: 即該難度等級。
        未指定 COURSE 時，慣例預設為 Oni。沒有的難度留 None。
        每個難度只取第一個出現的等級（避免連彈/分支重複覆蓋）。
        """
        levels: Dict[str, Optional[int]] = {d: None for d in DIFFICULTIES}
        current = "oni"      # 未標 COURSE 的單譜面慣例為鬼
        for raw in content.split("\n"):
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            up = line.upper()
            if up.startswith("COURSE:"):
                val = line.split(":", 1)[1].strip().lower()
                # 未知難度（如 tower/dan）→ None，後續 LEVEL 將被忽略
                current = COURSE_MAP.get(val)
                continue
            if up.startswith("LEVEL:"):
                if current is None or levels.get(current) is not None:
                    continue
                val = line.split(":", 1)[1].strip()
                try:
                    levels[current] = int(float(val))
                except ValueError:
                    pass
        return levels

    def parse_file(self, file_path: str) -> Optional[Dict[str, str]]:
        """
        解析單個 TJA 檔案

        Args:
            file_path: TJA 檔案路徑

        Returns:
            包含歌曲資訊的字典，如果解析失敗則返回 None
        """
        if not os.path.exists(file_path):
            print(f"✗ 檔案不存在: {file_path}")
            return None

        metadata = {
            'file_path': file_path,
            'file_name': os.path.basename(file_path),
            'directory': os.path.dirname(file_path)
        }

        try:
            with open(file_path, 'rb') as f:
                content = self.decode_bytes(f.read())
            if content is None:
                print(f"✗ 無法解碼檔案: {file_path}")
                return None
            metadata.update(self.parse_text(content))
            for diff, lv in self.parse_courses(content).items():
                metadata[f"level_{diff}"] = lv
            return metadata

        except Exception as e:
            print(f"✗ 解析檔案時發生錯誤 {file_path}: {e}")
            return None

    def get_category_from_path(self, file_path: str, base_dir: str = None) -> Optional[str]:
        """
        從檔案路徑提取分類名稱

        Args:
            file_path: 檔案路徑
            base_dir: 基礎目錄路徑

        Returns:
            分類名稱
        """
        path_parts = Path(file_path).parts

        # 尋找分類資料夾（通常以數字開頭）
        for part in path_parts:
            # 檢查是否符合分類格式（例如 "01 Pop", "02 Anime"）
            if re.match(r'^\d{2}\s+', part):
                return part

        return None

    def scan_directory(self, directory: str, recursive: bool = True) -> list:
        """
        掃描目錄中的所有 TJA 檔案

        Args:
            directory: 要掃描的目錄
            recursive: 是否遞迴掃描子目錄

        Returns:
            TJA 檔案路徑列表
        """
        tja_files = []

        if not os.path.exists(directory):
            print(f"✗ 目錄不存在: {directory}")
            return tja_files

        if recursive:
            # 遞迴掃描
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith('.tja'):
                        tja_files.append(os.path.join(root, file))
        else:
            # 只掃描當前目錄
            for file in os.listdir(directory):
                if file.lower().endswith('.tja'):
                    tja_files.append(os.path.join(directory, file))

        return tja_files

    def parse_directory(self, directory: str, recursive: bool = True,
                       show_progress: bool = True) -> list:
        """
        解析目錄中的所有 TJA 檔案

        Args:
            directory: 要掃描的目錄
            recursive: 是否遞迴掃描子目錄
            show_progress: 是否顯示進度

        Returns:
            包含所有歌曲資訊的列表
        """
        # 掃描 TJA 檔案
        tja_files = self.scan_directory(directory, recursive)

        if show_progress:
            print(f"找到 {len(tja_files)} 個 TJA 檔案")
            print("開始解析...")

        # 解析所有檔案
        songs = []
        for i, file_path in enumerate(tja_files, 1):
            if show_progress and i % 50 == 0:
                print(f"進度: {i}/{len(tja_files)} ({i*100//len(tja_files)}%)")

            metadata = self.parse_file(file_path)
            if metadata:
                # 添加分類資訊
                category = self.get_category_from_path(file_path, directory)
                if category:
                    metadata['category'] = category

                songs.append(metadata)

        if show_progress:
            print(f"✓ 成功解析 {len(songs)} 首歌曲")

        return songs


def main():
    """測試解析功能"""
    import sys

    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = r"Z:\[TJA ESE]\Songs\Songs"

    parser = TJAParser()

    if os.path.isfile(path):
        # 解析單個檔案
        print(f"解析檔案: {path}")
        print("=" * 60)
        metadata = parser.parse_file(path)
        if metadata:
            for key, value in metadata.items():
                print(f"{key}: {value}")
    elif os.path.isdir(path):
        # 解析目錄
        print(f"掃描目錄: {path}")
        print("=" * 60)
        songs = parser.parse_directory(path, recursive=True)

        # 顯示前 5 首
        print("\n前 5 首歌曲:")
        print("-" * 60)
        for song in songs[:5]:
            title = song.get('title', 'N/A')
            titleja = song.get('titleja', 'N/A')
            category = song.get('category', 'N/A')
            print(f"📄 {title}")
            print(f"   日文: {titleja}")
            print(f"   分類: {category}")
            print()
    else:
        print("請提供有效的檔案或目錄路徑")


if __name__ == "__main__":
    main()
