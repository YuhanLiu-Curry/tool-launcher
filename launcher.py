import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import subprocess
import socket
import threading
import webbrowser
import time
import urllib.request
import urllib.error
import ctypes
import ctypes.wintypes

# ---- Windows API ----
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

# Shell_NotifyIcon constants
NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 1
NIF_ICON = 2
NIF_TIP = 4
WM_TRAY_CALLBACK = 0x4000 + 1

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.c_ulong),
        ('hWnd', ctypes.wintypes.HWND),
        ('uID', ctypes.c_uint),
        ('uFlags', ctypes.c_uint),
        ('uCallbackMessage', ctypes.c_uint),
        ('hIcon', ctypes.wintypes.HICON),
        ('szTip', ctypes.c_wchar * 128),
    ]

# ---- Config ----
TOOLS_FILE = os.path.join(os.path.dirname(__file__), 'tools.json')
REFRESH_INTERVAL = 3000  # ms
FLOAT_W = 260
ROW_H = 44
HEADER_H = 36

# ---- Color scheme ----
BG_COLOR = '#f8fafc'
CARD_BORDER = '#e2e8f0'
TEXT_PRIMARY = '#1e293b'
TEXT_SECONDARY = '#64748b'
HOVER_BG = '#eef2ff'
GREEN = '#22c55e'
GRAY = '#94a3b8'
ORANGE = '#f59e0b'


# ========== Tool Manager ==========
class ToolManager:
    def __init__(self):
        self.tools = []
        self.processes = {}

    def load(self):
        with open(TOOLS_FILE, encoding='utf-8') as f:
            self.tools = json.load(f)

    def _extract_host_port(self, url):
        host = '127.0.0.1'
        port = None
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.hostname or '127.0.0.1'
            port = parsed.port
        except Exception:
            pass
        return host, port

    def is_running(self, tool):
        name = tool['name']
        proc = self.processes.get(name)
        if proc is not None:
            if proc.poll() is None:
                return True
            del self.processes[name]

        host, port = self._extract_host_port(tool['url'])
        if port is None:
            return False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def _kill_pid_tree(self, pid):
        try:
            subprocess.run(
                ['taskkill', '/f', '/t', '/pid', str(pid)],
                capture_output=True, timeout=5
            )
        except Exception:
            pass

    def start(self, tool):
        name = tool['name']
        proc = self.processes.get(name)
        if proc is not None and proc.poll() is None:
            return True

        cmd = tool.get('start', '').strip()
        if not cmd:
            return True

        work_dir = tool.get('dir', '') or None
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=work_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        self.processes[name] = proc

        time.sleep(1.5)
        if proc.poll() is not None:
            return False
        return True

    def stop(self, tool):
        name = tool['name']
        proc = self.processes.pop(name, None)
        if proc is None:
            return
        if proc.poll() is None:
            self._kill_pid_tree(proc.pid)

    def stop_all(self):
        for name in list(self.processes.keys()):
            proc = self.processes.pop(name, None)
            if proc is not None and proc.poll() is None:
                self._kill_pid_tree(proc.pid)

    def wait_until_ready(self, tool, timeout=10):
        url = tool['url']
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                urllib.request.urlopen(url, timeout=1)
                return True
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
        return False


# ========== Floating Widget GUI ==========
class ToolLauncher:
    def __init__(self, root):
        self.root = root
        self.manager = ToolManager()
        self.manager.load()

        self.rows = {}            # name -> dict of widgets
        self.starting_tools = set()
        self._collapsed = False

        self._setup_window()
        self._setup_tray()
        self._setup_ui()
        self._build_rows()
        self._start_status_poller()

    # ---- Window ----
    def _setup_window(self):
        self.root.title('🧰 工具箱')
        self.root.configure(bg='white')
        self.root.geometry(f'{FLOAT_W}x1')

        # Keep on top by default (user can toggle with pin button)
        self.root.attributes('-topmost', True)

        # Position — top-right corner, below the clock area
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f'+{sw - FLOAT_W - 20}+80')

        # Close → minimize to taskbar (window stays accessible via taskbar icon)
        self.root.protocol('WM_DELETE_WINDOW', self._minimize_window)

    # ---- System Tray Icon ----
    def _setup_tray(self):
        self.root.after(500, self._do_add_tray)

    def _do_add_tray(self):
        hwnd = self.root.winfo_id()

        self._nid = NOTIFYICONDATAW()
        self._nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self._nid.hWnd = hwnd
        self._nid.uID = 1
        self._nid.uFlags = NIF_MESSAGE | NIF_TIP
        self._nid.uCallbackMessage = WM_TRAY_CALLBACK
        self._nid.szTip = '🧰 工具箱'

        # Use standard application icon (not IDI_QUESTION)
        self._nid.uFlags |= NIF_ICON
        self._nid.hIcon = user32.LoadIconW(None, 32512)  # IDI_APPLICATION

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))
        print('Tray icon added')

        self._poll_tray()

    def _poll_tray(self):
        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, WM_TRAY_CALLBACK, WM_TRAY_CALLBACK, 1):
            if msg.message == WM_TRAY_CALLBACK:
                if msg.lParam == 0x202:  # WM_LBUTTONUP
                    self._toggle_window()
                elif msg.lParam == 0x205:  # WM_RBUTTONUP
                    self._show_tray_menu()
        self.root.after(200, self._poll_tray)

    def _remove_tray(self):
        try:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
        except Exception:
            pass

    def _show_tray_menu(self):
        pos = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pos))

        menu = tk.Menu(self.root, tearoff=0, font=('Segoe UI', 10))
        menu.add_command(label='📂 显示/隐藏', command=self._toggle_window)
        menu.add_separator()
        menu.add_command(label='⏹ 退出', command=self._quit)

        user32.SetForegroundWindow(self.root.winfo_id())
        menu.tk_popup(pos.x, pos.y)
        menu.bind('<Destroy>', lambda e: None)

    # ---- UI ----
    def _setup_ui(self):
        self.container = tk.Frame(self.root, bg='white', highlightbackground=CARD_BORDER, highlightthickness=1)
        self.container.pack(fill='both', expand=True)
        self.container.pack_propagate(False)

        # Header
        self.header = tk.Frame(self.container, bg='#f8fafc', height=HEADER_H)
        self.header.pack(fill='x')
        self.header.pack_propagate(False)

        self.header.bind('<Double-Button-1>', lambda e: self._toggle_collapse())
        self.header.bind('<Button-3>', lambda e: self._show_header_menu(e))

        self.title_lbl = tk.Label(
            self.header, text='🧰 工具箱', font=('Segoe UI', 11, 'bold'),
            bg='#f8fafc', fg=TEXT_PRIMARY
        )
        self.title_lbl.pack(side='left', padx=(10, 0))
        self.title_lbl.bind('<Double-Button-1>', lambda e: self._toggle_collapse())
        self.title_lbl.bind('<Button-3>', lambda e: self._show_header_menu(e))

        btn_frame = tk.Frame(self.header, bg='#f8fafc')
        btn_frame.pack(side='right', padx=(0, 4))

        self._btn_reload = tk.Label(
            btn_frame, text='⟳', font=('Segoe UI', 12),
            bg='#f8fafc', fg=TEXT_SECONDARY, cursor='hand2', padx=4
        )
        self._btn_reload.pack(side='left')
        self._btn_reload.bind('<Button-1>', lambda e: self._reload())
        self._btn_reload.bind('<Enter>', lambda e: self._btn_reload.configure(bg=HOVER_BG))
        self._btn_reload.bind('<Leave>', lambda e: self._btn_reload.configure(bg='#f8fafc'))

        self._btn_pin = tk.Label(
            btn_frame, text='📌', font=('Segoe UI', 10),
            bg='#f8fafc', fg='#6366f1', cursor='hand2', padx=4
        )
        self._btn_pin.pack(side='left')
        self._btn_pin.bind('<Button-1>', lambda e: self._toggle_pin())
        self._btn_pin.bind('<Enter>', lambda e: self._btn_pin.configure(bg=HOVER_BG))
        self._btn_pin.bind('<Leave>', lambda e: self._btn_pin.configure(bg='#f8fafc'))

        # Separator
        sep = tk.Frame(self.container, bg=CARD_BORDER, height=1)
        sep.pack(fill='x')
        self._sep = sep

        # Body
        self.body = tk.Frame(self.container, bg='white')
        self.body.pack(fill='both', expand=True, padx=0, pady=0)

        # Hint
        self.hint = tk.Label(
            self.container, text='双击顶栏折叠 · 右键菜单',
            font=('Segoe UI', 8), bg='white', fg=TEXT_SECONDARY
        )
        self.hint.pack(pady=(0, 4))

    # ---- Collapse ----
    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.body.pack_forget()
            self._sep.pack_forget()
            self.hint.pack_forget()
            self.container.configure(height=HEADER_H)
            self.root.geometry(f'{FLOAT_W}x{HEADER_H + 2}')
        else:
            self.body.pack(fill='both', expand=True, padx=0, pady=0)
            self._sep.pack(fill='x', before=self.body)
            self.hint.pack(pady=(0, 4))
            self._resize_window()

    # ---- Pin toggle ----
    def _toggle_pin(self):
        current = self.root.attributes('-topmost')
        self.root.attributes('-topmost', not current)
        self._btn_pin.configure(
            fg='#6366f1' if not current else TEXT_SECONDARY,
            text='📌' if not current else '📍'
        )

    # ---- Build tool rows ----
    def _build_rows(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.rows.clear()

        for tool in self.manager.tools:
            self._create_row(tool)

        self._resize_window()

    def _create_row(self, tool):
        name = tool['name']
        icon = tool.get('icon', '🔧')
        desc = tool.get('desc', '')

        row = tk.Frame(self.body, bg='white', height=ROW_H, cursor='hand2')
        row.pack(fill='x', padx=0)
        row.pack_propagate(False)

        row.bind('<Enter>', lambda e, r=row: self._row_enter(r))
        row.bind('<Leave>', lambda e, r=row: self._row_leave(r))

        line = tk.Frame(row, bg='#f1f5f9', height=1)
        line.pack(side='bottom', fill='x')

        icon_lbl = tk.Label(
            row, text=icon, font=('Segoe UI', 14),
            bg='white', width=2
        )
        icon_lbl.pack(side='left', padx=(10, 4))

        text_frame = tk.Frame(row, bg='white')
        text_frame.pack(side='left', fill='x', expand=True)

        name_lbl = tk.Label(
            text_frame, text=name, font=('Segoe UI', 10, 'bold'),
            bg='white', fg=TEXT_PRIMARY, anchor='w'
        )
        name_lbl.pack(fill='x', pady=(3, 0))

        desc_lbl = tk.Label(
            text_frame, text=desc, font=('Segoe UI', 8),
            bg='white', fg=TEXT_SECONDARY, anchor='w'
        )
        desc_lbl.pack(fill='x')

        status_lbl = tk.Label(
            row, text='○', font=('Segoe UI', 10),
            bg='white', fg=GRAY
        )
        status_lbl.pack(side='right', padx=(0, 10))

        for w in (row, icon_lbl, text_frame, name_lbl, desc_lbl):
            w.bind('<Button-1>', lambda e, t=tool: self._on_click(t))

        row.bind('<Button-3>', lambda e, t=tool: self._show_menu(e, t))

        self.rows[name] = {
            'row': row, 'status': status_lbl,
            'tool': tool, 'icon': icon_lbl,
            'name': name_lbl, 'desc': desc_lbl
        }

    def _row_enter(self, row):
        row.configure(bg=HOVER_BG)
        for w in row.winfo_children():
            if isinstance(w, tk.Label):
                w.configure(bg=HOVER_BG)
            elif isinstance(w, tk.Frame):
                for c in w.winfo_children():
                    if isinstance(c, tk.Label):
                        c.configure(bg=HOVER_BG)
        for w in row.winfo_children():
            if isinstance(w, tk.Frame) and w.winfo_height() == 1:
                w.configure(bg=HOVER_BG)

    def _row_leave(self, row):
        row.configure(bg='white')
        for w in row.winfo_children():
            if isinstance(w, tk.Label):
                w.configure(bg='white')
            elif isinstance(w, tk.Frame):
                for c in w.winfo_children():
                    if isinstance(c, tk.Label):
                        c.configure(bg='white')
        for w in row.winfo_children():
            if isinstance(w, tk.Frame) and w.winfo_height() == 1:
                w.configure(bg='#f1f5f9')

    def _resize_window(self):
        n = len(self.manager.tools)
        h = HEADER_H + 2 + n * ROW_H + 24
        self.container.configure(height=h)
        self.root.geometry(f'{FLOAT_W}x{h}')

    # ---- Click ----
    def _on_click(self, tool):
        name = tool['name']
        if name in self.starting_tools:
            return

        self._set_status(name, '⟳', ORANGE)
        self.starting_tools.add(name)

        def launch():
            try:
                if tool.get('start', '').strip():
                    ok = self.manager.start(tool)
                    if not ok:
                        self.root.after(0, lambda: self._set_status(name, '✕', '#ef4444'))
                        return
                    ready = self.manager.wait_until_ready(tool, timeout=12)
                    if not ready:
                        self.root.after(0, lambda: self._set_status(name, '✕', '#ef4444'))
                        return
                webbrowser.open(tool['url'])
                self.root.after(0, lambda: self._update_status(name))
            finally:
                self.starting_tools.discard(name)

        threading.Thread(target=launch, daemon=True).start()

    def _set_status(self, name, text, color):
        if name in self.rows:
            self.rows[name]['status'].configure(text=text, fg=color)

    # ---- Right-click menu ----
    def _show_menu(self, event, tool):
        menu = tk.Menu(self.root, tearoff=0, font=('Segoe UI', 10))
        name = tool['name']
        running = self.manager.is_running(tool)

        if running:
            menu.add_command(label='⏹ 停止', command=lambda: self._stop_tool(tool))
        menu.add_command(label='🌐 打开', command=lambda: webbrowser.open(tool['url']))
        menu.add_separator()
        menu.add_command(label='✕ 移除此工具', command=lambda: self._remove_tool(name))
        menu.tk_popup(event.x_root, event.y_root)

    def _show_header_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0, font=('Segoe UI', 10))
        menu.add_command(label='🔄 重载配置', command=self._reload)
        menu.add_separator()
        menu.add_command(label='⏹ 退出工具箱', command=self._quit)
        menu.tk_popup(event.x_root, event.y_root)

    def _stop_tool(self, tool):
        self.manager.stop(tool)
        self._update_status(tool['name'])

    def _remove_tool(self, name):
        self.manager.tools = [t for t in self.manager.tools if t['name'] != name]
        self._save_tools()
        self._build_rows()

    def _save_tools(self):
        with open(TOOLS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.manager.tools, f, ensure_ascii=False, indent=2)

    # ---- Status polling ----
    def _start_status_poller(self):
        self._poll_status()
        self.root.after(REFRESH_INTERVAL, self._start_status_poller)

    def _poll_status(self):
        for name, widgets in self.rows.items():
            if name in self.starting_tools:
                continue
            self._update_status(name)

    def _update_status(self, name):
        if name not in self.rows:
            return
        tool = self.rows[name]['tool']
        running = self.manager.is_running(tool)
        lbl = self.rows[name]['status']
        lbl.configure(text='●' if running else '○', fg=GREEN if running else GRAY)

    # ---- Window management (taskbar-based) ----
    def _minimize_window(self):
        """Close button → minimize to taskbar."""
        self.root.iconify()

    def _restore_window(self):
        """Restore from minimized state."""
        self.root.deiconify()
        hwnd = self.root.winfo_id()
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        self.root.attributes('-topmost', True)
        self._btn_pin.configure(fg='#6366f1', text='📌')
        self.root.focus_force()

    def _toggle_window(self):
        """Tray icon click → toggle between minimized and normal."""
        state = self.root.state()
        if state == 'iconic' or state == 'withdrawn':
            self._restore_window()
        else:
            self._minimize_window()

    # ---- Actions ----
    def _reload(self):
        try:
            self.manager.load()
            self._build_rows()
        except Exception as e:
            messagebox.showerror('错误', f'读取 tools.json 失败:\n{e}')

    def _quit(self):
        if messagebox.askokcancel('退出', '确定退出工具箱？所有工具服务将被停止。'):
            self._remove_tray()
            self.manager.stop_all()
            self.root.destroy()


# ========== Entry ==========
def run():
    root = tk.Tk()
    launcher = ToolLauncher(root)
    root.mainloop()


if __name__ == '__main__':
    run()
