# utils/update.py
import sys
import hashlib
import requests
import logging
from .proxy_config import get_global_proxy

def get_file_sha256(file_path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()

def check_update() -> None:
    """
    检查exe是否为最新版本，开发环境跳过
    """
    proxy = get_global_proxy()
    proxies = proxy if proxy else None
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        try:
            logging.info("🔍 开始检查程序版本...")
            local_sha256 = get_file_sha256(exe_path)
            api_url = 'https://api.github.com/repos/kisekinoumi/mzzbscore/releases/latest'
            resp = requests.get(api_url, timeout=10, proxies=proxies)
            if resp.status_code == 200:
                data = resp.json()
                remote_sha256 = None
                for asset in data.get('assets', []):
                    if asset['name'] == 'mzzb_score.exe':
                        digest = asset.get('digest', '')
                        if digest.startswith('sha256:'):
                            remote_sha256 = digest.split(':', 1)[1]
                        break
                if remote_sha256:
                    logging.info(f"本地sha256: {local_sha256}")
                    logging.info(f"最新release sha256: {remote_sha256}")
                    if local_sha256 != remote_sha256:
                        logging.warning("❌ 检测到新版本，建议前往GitHub下载最新版 mzzb_score.exe")
                    else:
                        logging.info("✅ 当前已是最新版，无需更新")
                else:
                    logging.warning("❌ 未找到最新release的mzzb_score.exe文件或sha256信息，无法检查更新")
            else:
                logging.warning("❌ 无法访问GitHub以检查更新")
        except Exception as e:
            logging.warning(f"❌ 检查更新时发生错误: {e}\n无法访问GitHub以检查更新")
    else:
        logging.info("当前运行在开发环境（python），跳过更新检查")
