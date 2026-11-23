import os
import sys
import shutil
import subprocess
import threading
import winreg
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "跨设备传输"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "CrossDeviceTransfer"
EXE_NAME = "跨设备传输.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CrossDeviceTransfer"


def get_payload_exe():
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "payload", EXE_NAME)


def default_install_dir():
    local_app = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local_app, "Programs", APP_NAME)


def create_shortcut(lnk_path, target_path, work_dir, desc=""):
    os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
    ps_script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{lnk_path.replace(chr(39), chr(39)*2)}'); "
        f"$sc.TargetPath = '{target_path.replace(chr(39), chr(39)*2)}'; "
        f"$sc.WorkingDirectory = '{work_dir.replace(chr(39), chr(39)*2)}'; "
        f"$sc.IconLocation = '{target_path.replace(chr(39), chr(39)*2)},0'; "
        f"$sc.Description = '{desc.replace(chr(39), chr(39)*2)}'; "
        "$sc.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def write_uninstaller(install_dir, desktop_lnk, startmenu_dir):
    uninst_bat = os.path.join(install_dir, "卸载跨设备传输.bat")
    bat_content = f"""@echo off
chcp 65001 >nul
title 卸载 {APP_NAME}
echo 正在关闭并卸载 {APP_NAME}...
taskkill /F /IM "{EXE_NAME}" >nul 2>&1
timeout /t 1 /nobreak >nul
del /F /Q "{desktop_lnk}" >nul 2>&1
rmdir /S /Q "{startmenu_dir}" >nul 2>&1
reg delete "HKCU\\{UNINSTALL_KEY}" /f >nul 2>&1
del /F /Q "{os.path.join(install_dir, EXE_NAME)}" >nul 2>&1
echo.
echo 已完成卸载！注：您保存的文件文件夹（我接收的文件 / 电脑待分享的文件）已保留。
echo 如需彻底删除，请手动删除目录：{install_dir}
pause
"""
    with open(uninst_bat, "w", encoding="utf-8") as f:
        f.write(bat_content)
    return uninst_bat


def register_uninstall(install_dir, exe_path, uninst_bat):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, f"{exe_path},0")
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'cmd.exe /c "{uninst_bat}"')
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"安装 {APP_NAME} v{APP_VERSION}")
        self.root.geometry("500x360")
        self.root.resizable(False, False)
        self.root.configure(bg="#FAFAF9")

        self.dir_var = tk.StringVar(value=default_install_dir())
        self.desktop_var = tk.BooleanVar(value=True)
        self.startmenu_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="准备就绪，点击下方按钮开始安装")

        self._build_ui()

    def _build_ui(self):
        wrap = tk.Frame(self.root, bg="#FAFAF9", padx=28, pady=22)
        wrap.pack(fill="both", expand=True)

        hd = tk.Frame(wrap, bg="#FAFAF9")
        hd.pack(fill="x", pady=(0, 14))
        tk.Label(hd, text=" ⇄ ", font=("Segoe UI", 13, "bold"), bg="#16161A", fg="#10B981").pack(side="left")
        tk.Label(hd, text=f"  {APP_NAME} 安装向导", font=("微软雅黑", 14, "bold"), bg="#FAFAF9", fg="#16161A").pack(side="left")
        tk.Label(hd, text=f"v{APP_VERSION}", font=("Consolas", 9), bg="#FAFAF9", fg="#6B6B73").pack(side="right", pady=(6, 0))

        card = tk.Frame(wrap, bg="#FFFFFF", relief="solid", bd=1, padx=16, pady=14)
        card.pack(fill="x", pady=(0, 12))

        tk.Label(card, text="安装目录（无需管理员权限，自动创建收发文件夹）", font=("微软雅黑", 9), bg="#FFFFFF", fg="#6B6B73").pack(anchor="w")
        row = tk.Frame(card, bg="#FFFFFF")
        row.pack(fill="x", pady=(6, 10))
        tk.Entry(row, textvariable=self.dir_var, font=("Consolas", 9), relief="solid", bd=1).pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(row, text="浏览...", font=("微软雅黑", 9), bg="#FAFAF9", fg="#16161A", relief="solid", bd=1, padx=10, cursor="hand2", command=self._browse).pack(side="right", padx=(8, 0))

        opts = tk.Frame(card, bg="#FFFFFF")
        opts.pack(fill="x")
        tk.Checkbutton(opts, text="创建桌面快捷方式", variable=self.desktop_var, bg="#FFFFFF", fg="#16161A", font=("微软雅黑", 9), activebackground="#FFFFFF").pack(anchor="w")
        tk.Checkbutton(opts, text="添加到开始菜单（含卸载入口）", variable=self.startmenu_var, bg="#FFFFFF", fg="#16161A", font=("微软雅黑", 9), activebackground="#FFFFFF").pack(anchor="w")
        tk.Checkbutton(opts, text="安装完成后立即启动", variable=self.launch_var, bg="#FFFFFF", fg="#16161A", font=("微软雅黑", 9), activebackground="#FFFFFF").pack(anchor="w")

        self.progress = ttk.Progressbar(wrap, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(4, 6))

        tk.Label(wrap, textvariable=self.status_var, font=("微软雅黑", 9), bg="#FAFAF9", fg="#6B6B73").pack(anchor="w", pady=(0, 10))

        self.install_btn = tk.Button(
            wrap,
            text="立即安装",
            font=("微软雅黑", 10, "bold"),
            bg="#16161A",
            fg="#FFFFFF",
            activebackground="#065F46",
            activeforeground="#FFFFFF",
            relief="flat",
            pady=9,
            cursor="hand2",
            command=self._start_install,
        )
        self.install_btn.pack(fill="x")

    def _browse(self):
        chosen = filedialog.askdirectory(initialdir=self.dir_var.get(), title="选择安装目录")
        if chosen:
            if os.path.basename(chosen) != APP_NAME:
                chosen = os.path.join(chosen, APP_NAME)
            self.dir_var.set(chosen)

    def _set_state(self, pct, msg):
        self.root.after(0, lambda: (self.progress.configure(value=pct), self.status_var.set(msg)))

    def _start_install(self):
        install_dir = self.dir_var.get().strip()
        if not install_dir:
            messagebox.showwarning("提示", "请选择有效的安装目录")
            return
        self.install_btn.configure(state="disabled", text="正在安装...")
        threading.Thread(target=self._do_install, args=(install_dir,), daemon=True).start()

    def _do_install(self, install_dir):
        try:
            payload = get_payload_exe()
            if not os.path.exists(payload):
                raise FileNotFoundError(f"安装包内缺少主程序：{payload}")

            self._set_state(15, "正在创建安装目录...")
            os.makedirs(install_dir, exist_ok=True)
            os.makedirs(os.path.join(install_dir, "我接收的文件"), exist_ok=True)
            os.makedirs(os.path.join(install_dir, "电脑待分享的文件"), exist_ok=True)

            # 若旧进程运行中，先优雅关闭以便覆盖更新
            subprocess.run(
                ["taskkill", "/F", "/IM", EXE_NAME],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            self._set_state(45, f"正在复制 {EXE_NAME}...")
            target_exe = os.path.join(install_dir, EXE_NAME)
            shutil.copy2(payload, target_exe)

            desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
            desktop_lnk = os.path.join(desktop_dir, f"{APP_NAME}.lnk")
            startmenu_dir = os.path.join(
                os.environ.get("APPDATA", os.path.expanduser("~")),
                "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME
            )

            self._set_state(70, "正在写入卸载脚本与系统应用注册表...")
            uninst_bat = write_uninstaller(install_dir, desktop_lnk, startmenu_dir)
            register_uninstall(install_dir, target_exe, uninst_bat)

            if self.desktop_var.get():
                self._set_state(82, "正在创建桌面快捷方式...")
                create_shortcut(desktop_lnk, target_exe, install_dir, f"{APP_NAME} - 跨设备极速文件传输")

            if self.startmenu_var.get():
                self._set_state(92, "正在创建开始菜单快捷方式...")
                create_shortcut(os.path.join(startmenu_dir, f"{APP_NAME}.lnk"), target_exe, install_dir, APP_NAME)
                create_shortcut(os.path.join(startmenu_dir, f"卸载 {APP_NAME}.lnk"), uninst_bat, install_dir, f"卸载 {APP_NAME}")

            self._set_state(100, f"安装完成！位置：{install_dir}")

            def _finish():
                self.install_btn.configure(state="normal", text="完成并关闭", command=self.root.destroy)
                if self.launch_var.get():
                    try:
                        os.startfile(target_exe)
                    except Exception:
                        pass
                messagebox.showinfo("安装成功", f"{APP_NAME} 已成功安装到：\n{install_dir}")
                self.root.destroy()

            self.root.after(0, _finish)
        except Exception as e:
            def _fail():
                self.install_btn.configure(state="normal", text="重试安装")
                self.status_var.set(f"安装失败：{e}")
                messagebox.showerror("安装失败", str(e))
            self.root.after(0, _fail)


if __name__ == "__main__":
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()
