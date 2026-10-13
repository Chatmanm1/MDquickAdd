import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
from datetime import datetime
import threading
import ctypes

def verify_dependencies():
    """Verify system requirements and install missing packages."""
    required_packages = {
        "keyboard": "keyboard",
        "pystray": "pystray",
        "PIL": "Pillow"
    }
    for module, package in required_packages.items():
        try:
            __import__(module)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

verify_dependencies()

import keyboard
import pystray
from PIL import Image, ImageDraw

CONFIG_FILE = "app_settings.json"
ICON_FILE = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "quick_input_icon.ico")

def generate_icon_image():
    """Generate a placeholder icon image for the system tray and taskbar."""
    image = Image.new('RGB', (64, 64), color=(30, 30, 30))
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, 48, 48), fill=(100, 150, 255))
    return image

def setup_windows_taskbar_icon():
    """Set the AppUserModelID to ensure the taskbar groups the icon correctly."""
    if os.name == 'nt':
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("custom.quick.input.v1.6")
        except Exception:
            pass

def apply_dark_titlebar(window):
    """Apply immersive dark mode to the Windows DWM title bar."""
    if os.name == 'nt':
        try:
            window.update()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            get_parent = ctypes.windll.user32.GetParent
            hwnd = get_parent(window.winfo_id())
            value = ctypes.c_int(2)
            set_window_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

class PersistentTextBox:
    """Main application class for the persistent text interface with default append mode."""
    def __init__(self):
        setup_windows_taskbar_icon()
        
        self.root = tk.Tk()
        self.root.title("Quick Input")
        self.root.geometry("500x400")
        self.root.configure(bg="#1e1e1e")
        self.root.protocol("WM_DELETE_WINDOW", self.hide_interface)
        
        if not os.path.exists(ICON_FILE):
            generate_icon_image().save(ICON_FILE, format="ICO")
        try:
            self.root.iconbitmap(ICON_FILE)
        except Exception:
            pass

        apply_dark_titlebar(self.root)
        self.load_settings()
        self.setup_styles()
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)
        
        self.tab_input = tk.Frame(self.notebook, bg="#1e1e1e")
        self.tab_settings = tk.Frame(self.notebook, bg="#1e1e1e")
        
        self.notebook.add(self.tab_input, text="Input")
        self.notebook.add(self.tab_settings, text="Settings")
        
        self.build_input_tab()
        self.build_settings_tab()
        
        self.activation_flag = False
        self.active_mode = "APPEND"
        self.settings_flag = False
        self.quit_flag = False
        
        keyboard.add_hotkey('ctrl+shift+space', self.trigger_activation_append)
        keyboard.add_hotkey('ctrl+alt+space', self.trigger_activation_new)
        
        self.start_system_tray()
        self.hide_interface()
        self.poll_flags()
        self.root.mainloop()

    def setup_styles(self):
        """Configure ttk styles for dark mode tabs."""
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background='#1e1e1e', borderwidth=0)
        style.configure('TNotebook.Tab', background='#2d2d2d', foreground='#d4d4d4', padding=[15, 5], borderwidth=0)
        style.map('TNotebook.Tab', 
                  background=[('selected', '#3c3c3c'), ('active', '#323232')], 
                  foreground=[('selected', '#ffffff')])

    def build_input_tab(self):
        """Construct the main text input area."""
        self.text_area = tk.Text(
            self.tab_input, wrap="word", font=("Arial", 12), 
            bg="#2d2d2d", fg="#d4d4d4", insertbackground="white", 
            relief="flat", padx=10, pady=10
        )
        self.text_area.pack(expand=True, fill="both", padx=5, pady=5)
        
        bottom_frame = tk.Frame(self.tab_input, bg="#1e1e1e")
        bottom_frame.pack(fill="x", padx=5, pady=(0, 5))
        
        self.status_label = tk.Label(bottom_frame, text="Press Ctrl+Enter to save", bg="#1e1e1e", fg="#888888")
        self.status_label.pack(side="left")
        
        self.text_area.bind("<Control-Return>", self.save_file)

    def build_settings_tab(self):
        """Construct the settings directory and file selection interface."""
        container = tk.Frame(self.tab_settings, bg="#1e1e1e")
        container.pack(expand=True, fill="both", padx=20, pady=20)
        
        # Append File Settings (Now Primary)
        tk.Label(container, text="Append File Target (Ctrl+Shift+Space):", bg="#1e1e1e", fg="#d4d4d4", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        self.file_var = tk.StringVar(value=self.append_file)
        file_entry = tk.Entry(
            container, textvariable=self.file_var, state="readonly", 
            width=50, bg="#2d2d2d", fg="#d4d4d4", readonlybackground="#2d2d2d", relief="flat", font=("Arial", 10)
        )
        file_entry.pack(fill="x", pady=5)
        
        def choose_file():
            file_path = filedialog.askopenfilename(
                initialdir=os.path.dirname(self.append_file) if self.append_file else "",
                filetypes=[("Markdown Files", "*.md"), ("Text Files", "*.txt"), ("All Files", "*.*")]
            )
            if file_path:
                self.append_file = file_path
                self.file_var.set(file_path)
                self.save_settings()
                self.status_label.config(text="Append file updated.")

        tk.Button(
            container, text="Browse File...", command=choose_file, 
            bg="#3c3c3c", fg="#d4d4d4", activebackground="#505050", 
            activeforeground="#ffffff", relief="flat", width=20
        ).pack(anchor="e", pady=(0, 15))

        # New Note Directory Settings (Now Secondary)
        tk.Label(container, text="New Note Directory (Ctrl+Alt+Space):", bg="#1e1e1e", fg="#d4d4d4", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 5))
        
        self.dir_var = tk.StringVar(value=self.save_dir)
        dir_entry = tk.Entry(
            container, textvariable=self.dir_var, state="readonly", 
            width=50, bg="#2d2d2d", fg="#d4d4d4", readonlybackground="#2d2d2d", relief="flat", font=("Arial", 10)
        )
        dir_entry.pack(fill="x", pady=5)
        
        def choose_dir():
            folder = filedialog.askdirectory(initialdir=self.save_dir)
            if folder:
                self.save_dir = folder
                self.dir_var.set(folder)
                self.save_settings()
                self.status_label.config(text="Save directory updated.")
                
        tk.Button(
            container, text="Browse Directory...", command=choose_dir, 
            bg="#3c3c3c", fg="#d4d4d4", activebackground="#505050", 
            activeforeground="#ffffff", relief="flat", width=20
        ).pack(anchor="e", pady=0)

    def load_settings(self):
        """Retrieve configurations from local JSON storage."""
        self.save_dir = ""
        self.append_file = ""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.save_dir = data.get("save_dir", "")
                    self.append_file = data.get("append_file", "")
            except json.JSONDecodeError:
                pass

    def save_settings(self):
        """Write current configurations to local JSON storage."""
        with open(CONFIG_FILE, "w") as f:
            json.dump({"save_dir": self.save_dir, "append_file": self.append_file}, f)

    def trigger_activation_append(self):
        self.active_mode = "APPEND"
        self.activation_flag = True

    def trigger_activation_new(self):
        self.active_mode = "NEW"
        self.activation_flag = True

    def trigger_settings(self):
        self.settings_flag = True

    def save_file(self, event=None):
        """Process the text area contents based on the active mode."""
        content = self.text_area.get("1.0", tk.END).strip()
        if not content:
            self.status_label.config(text="Text box is empty. Not saved.")
            return "break"

        if self.active_mode == "APPEND":
            if not self.append_file or not os.path.exists(self.append_file):
                messagebox.showwarning("Configuration Error", "Please configure a valid append file target in the Settings tab.")
                self.notebook.select(self.tab_settings)
                return "break"
                
            try:
                with open(self.append_file, "a", encoding="utf-8") as f:
                    f.write(f"\n\n{content}")
                self.status_label.config(text=f"Appended to: {os.path.basename(self.append_file)}")
                self.text_area.delete("1.0", tk.END)
                self.hide_interface()
            except Exception as e:
                messagebox.showerror("Append Error", f"Failed to append to file: {e}")

        elif self.active_mode == "NEW":
            if not self.save_dir or not os.path.isdir(self.save_dir):
                messagebox.showwarning("Configuration Error", "Please configure a valid save directory in the Settings tab.")
                self.notebook.select(self.tab_settings)
                return "break"
                
            filename = f"{datetime.now().strftime('%y%m%d%H%M')}QN.md"
            filepath = os.path.join(self.save_dir, filename)
            formatted_content = f"---\nquick note: true\n---\n\n{content}"
            
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(formatted_content)
                self.status_label.config(text=f"Saved: {filename}")
                self.text_area.delete("1.0", tk.END)
                self.hide_interface()
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save file: {e}")
            
        return "break"

    def poll_flags(self):
        """Check asynchronous flags safely within the main Tkinter thread."""
        if self.activation_flag:
            if self.active_mode == "APPEND":
                self.status_label.config(text="Mode: APPEND NOTE | Press Ctrl+Enter to save")
            elif self.active_mode == "NEW":
                self.status_label.config(text="Mode: NEW NOTE | Press Ctrl+Enter to save")
                
            self.show_interface()
            self.notebook.select(self.tab_input)
            self.activation_flag = False
            
        if self.settings_flag:
            self.show_interface()
            self.notebook.select(self.tab_settings)
            self.settings_flag = False
            
        if self.quit_flag:
            self.root.quit()
            return
            
        self.root.after(100, self.poll_flags)

    def show_interface(self):
        """Display the text box and force focus."""
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(10, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()
        self.text_area.focus_set()

    def hide_interface(self):
        """Remove the window from the display while keeping the process active in tray."""
        self.root.withdraw()

    def start_system_tray(self):
        """Initialize the system tray icon in a separate thread."""
        def on_show_append(icon, item):
            self.trigger_activation_append()
            
        def on_show_new(icon, item):
            self.trigger_activation_new()
            
        def on_settings(icon, item):
            self.settings_flag = True
            
        def on_quit(icon, item):
            self.quit_flag = True
            icon.stop()
            
        menu = pystray.Menu(
            pystray.MenuItem('Append to File', on_show_append, default=True),
            pystray.MenuItem('New Quick Note', on_show_new),
            pystray.MenuItem('Settings', on_settings),
            pystray.MenuItem('Quit', on_quit)
        )
        
        self.tray_icon = pystray.Icon("Quick Input", generate_icon_image(), "Quick Input", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

if __name__ == "__main__":
    PersistentTextBox()
