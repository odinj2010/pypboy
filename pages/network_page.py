# pages/network_page.py
import customtkinter as ctk
from tkinter import messagebox
import threading
import logging
import subprocess
import sys
import socket

# --- Conditional Imports for Network Tools ---
NMAP_AVAILABLE = False
try:
    import nmap
    NMAP_AVAILABLE = True
except ImportError:
    pass

SCAPY_AVAILABLE = False
try:
    from scapy.all import srp, Ether, ARP
    SCAPY_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger(__name__)

# --- UI Constants ---
PIPBOY_GREEN = "#32f178"
PIPBOY_FRAME = "#2a2d2e"
MAIN_BG_COLOR = "#1a1a1a"
HACKER_FONT = ("Monaco", 10)
NODE_COLOR = "#1F6AA5"
NODE_TEXT_COLOR = "#FFFFFF"

class NetworkPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=MAIN_BG_COLOR)
        self.controller = controller
        self.scanner_thread = None
        self.is_scanning_network = False
        self.network_nodes = {} # Store canvas item IDs and their info

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        header.columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="NETWORK OPERATIONS", font=("Arial", 20, "bold"), text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Back to Home", command=lambda: self.controller.show_page("HomePage")).grid(row=0, column=1, sticky="e")

        self.tab_view = ctk.CTkTabview(self, fg_color=PIPBOY_FRAME)
        self.tab_view.add("Network Map")
        self.tab_view.add("Wi-Fi Scan")
        self.tab_view.add("Port Scanner")
        self.tab_view.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self._setup_network_map_tab()
        self._setup_wifi_tab()
        self._setup_port_scanner_tab()

    def _setup_network_map_tab(self):
        tab = self.tab_view.tab("Network Map")
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        controls_frame = ctk.CTkFrame(tab, fg_color="transparent")
        controls_frame.pack(pady=10, fill="x", padx=10)
        self.scan_network_button = ctk.CTkButton(controls_frame, text="Scan Local Network", command=self.start_network_scan)
        self.scan_network_button.pack(side="left")
        self.network_status_label = ctk.CTkLabel(controls_frame, text="Ready to scan for devices.")
        self.network_status_label.pack(side="left", padx=10)
        
        canvas_frame = ctk.CTkFrame(tab, fg_color=MAIN_BG_COLOR)
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.network_canvas = ctk.CTkCanvas(canvas_frame, bg=MAIN_BG_COLOR, highlightthickness=0)
        self.network_canvas.pack(fill="both", expand=True)

        if not SCAPY_AVAILABLE:
            self.network_status_label.configure(text="Scapy library not found. Network mapping disabled.")

    def _setup_wifi_tab(self):
        tab = self.tab_view.tab("Wi-Fi Scan")
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        
        ctk.CTkButton(tab, text="Scan for Wi-Fi Networks", command=self.start_wifi_scan).pack(pady=10)
        self.wifi_results_text = ctk.CTkTextbox(tab, font=HACKER_FONT, wrap="word", state="disabled")
        self.wifi_results_text.pack(fill="both", expand=True, padx=10, pady=10)
        if "linux" not in sys.platform:
             self._update_textbox(self.wifi_results_text, "Wi-Fi scanning is only supported on Linux.")

    def _setup_port_scanner_tab(self):
        tab = self.tab_view.tab("Port Scanner")
        tab.grid_rowconfigure(2, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        
        entry_frame = ctk.CTkFrame(tab, fg_color="transparent")
        entry_frame.pack(pady=10, fill="x", padx=10)
        entry_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(entry_frame, text="Target IP:").grid(row=0, column=0, padx=5)
        self.target_ip_entry = ctk.CTkEntry(entry_frame, placeholder_text="e.g., 192.168.1.1 or select from map")
        self.target_ip_entry.grid(row=0, column=1, sticky="ew")
        self.port_scan_button = ctk.CTkButton(entry_frame, text="Scan Ports", command=self.start_port_scan)
        self.port_scan_button.grid(row=0, column=2, padx=5)

        self.port_results_text = ctk.CTkTextbox(tab, font=HACKER_FONT, wrap="word", state="disabled")
        self.port_results_text.pack(fill="both", expand=True, padx=10, pady=10)
        if not NMAP_AVAILABLE:
            self._update_textbox(self.port_results_text, "python-nmap not found and/or nmap is not in system PATH.\nPort scanner disabled.")

    def _update_textbox(self, textbox, content, append=False):
        textbox.configure(state="normal")
        if not append:
            textbox.delete("1.0", "end")
        textbox.insert("end", content)
        textbox.configure(state="disabled")
        textbox.see("end")

    def start_network_scan(self):
        if not SCAPY_AVAILABLE:
            messagebox.showerror("Dependency Missing", "Scapy is required for network mapping.", parent=self)
            return
        if self.is_scanning_network:
            return

        self.is_scanning_network = True
        self.scan_network_button.configure(state="disabled")
        self.network_status_label.configure(text="Scanning... This may take a minute.")
        self.network_canvas.delete("all")
        self.network_nodes.clear()
        
        threading.Thread(target=self._network_scan_thread, daemon=True).start()

    def _network_scan_thread(self):
        try:
            # Get local IP and subnet to scan
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            ip_parts = local_ip.split('.')
            subnet = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.0/24"
            
            self.after(0, self.network_status_label.configure, {"text": f"Scanning subnet {subnet}..."})

            arp_request = ARP(pdst=subnet)
            broadcast = Ether(dst="ff:ff:ff:ff:ff:ff")
            arp_request_broadcast = broadcast / arp_request
            answered_list = srp(arp_request_broadcast, timeout=5, verbose=False)[0]

            clients = []
            for sent, received in answered_list:
                clients.append({'ip': received.psrc, 'mac': received.hwsrc})
            
            self.after(0, self._draw_network_map, clients)

        except Exception as e:
            logger.error(f"Network scan failed: {e}")
            self.after(0, self.network_status_label.configure, {"text": f"Error: {e}"})
        finally:
            self.is_scanning_network = False
            self.after(0, self.scan_network_button.configure, {"state": "normal"})

    def _draw_network_map(self, clients):
        self.network_canvas.delete("all")
        self.network_status_label.configure(text=f"Scan complete. Found {len(clients)} devices.")
        
        if not clients: return

        width = self.network_canvas.winfo_width()
        height = self.network_canvas.winfo_height()
        center_x, center_y = width / 2, height / 2
        radius = min(width, height) / 3
        angle_step = 360 / len(clients)

        for i, client in enumerate(clients):
            angle = np.deg2rad(i * angle_step)
            x = center_x + radius * np.cos(angle)
            y = center_y + radius * np.sin(angle)
            
            node_id = self.network_canvas.create_oval(x-20, y-20, x+20, y+20, fill=NODE_COLOR, outline=PIPBOY_GREEN, width=2)
            text_id = self.network_canvas.create_text(x, y + 30, text=client['ip'], fill=NODE_TEXT_COLOR, font=HACKER_FONT)
            
            self.network_nodes[node_id] = client
            self.network_nodes[text_id] = client
            
            self.network_canvas.tag_bind(node_id, "<Button-1>", lambda e, c=client: self._on_node_click(c))
            self.network_canvas.tag_bind(text_id, "<Button-1>", lambda e, c=client: self._on_node_click(c))

    def _on_node_click(self, client_info):
        ip = client_info['ip']
        self.tab_view.set("Port Scanner")
        self.target_ip_entry.delete(0, "end")
        self.target_ip_entry.insert(0, ip)
        self.start_port_scan()

    def start_wifi_scan(self):
        if "linux" not in sys.platform:
            messagebox.showwarning("Unsupported OS", "Wi-Fi scanning with nmcli is only supported on Linux.", parent=self)
            return
        self._update_textbox(self.wifi_results_text, "Scanning for Wi-Fi networks...\nThis may take a moment.\n\n")
        threading.Thread(target=self._wifi_scan_thread, daemon=True).start()

    def _wifi_scan_thread(self):
        try:
            cmd = "nmcli -f SSID,SIGNAL,SECURITY dev wifi"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                self.after(0, self._update_textbox, self.wifi_results_text, result.stdout)
            else:
                self.after(0, self._update_textbox, self.wifi_results_text, f"Error scanning Wi-Fi:\n{result.stderr}")
        except FileNotFoundError:
             self.after(0, self._update_textbox, self.wifi_results_text, "Error: 'nmcli' command not found. Is NetworkManager installed?")
        except Exception as e:
            self.after(0, self._update_textbox, self.wifi_results_text, f"An unexpected error occurred: {e}")

    def start_port_scan(self):
        if not NMAP_AVAILABLE:
            messagebox.showerror("Dependency Missing", "nmap is required for port scanning.", parent=self)
            return
        target = self.target_ip_entry.get().strip()
        if not target:
            messagebox.showwarning("Input Required", "Please enter a target IP address.", parent=self)
            return
        
        self.port_scan_button.configure(state="disabled")
        self._update_textbox(self.port_results_text, f"Starting Nmap scan on {target}...\n\n")
        threading.Thread(target=self._port_scan_thread, args=(target,), daemon=True).start()

    def _port_scan_thread(self, target):
        try:
            nm = nmap.PortScanner()
            nm.scan(target, arguments='-sV --top-ports 20')
            output = ""
            if not nm.all_hosts():
                output = "Host seems to be down or not responding."
            else:
                for host in nm.all_hosts():
                    output += f"Host: {host} ({nm[host].hostname()})\n"
                    output += f"State: {nm[host].state()}\n"
                    for proto in nm[host].all_protocols():
                        output += f"----------\nProtocol: {proto}\n"
                        ports = nm[host][proto].keys()
                        for port in sorted(ports):
                            state = nm[host][proto][port]['state']
                            name = nm[host][proto][port]['name']
                            product = nm[host][proto][port]['product']
                            version = nm[host][proto][port]['version']
                            output += f"Port: {port:<5} State: {state:<10} Service: {name} {product} {version}\n"
            self.after(0, self._update_textbox, self.port_results_text, output)
        except Exception as e:
            self.after(0, self._update_textbox, self.port_results_text, f"An error occurred during scan: {e}")
        finally:
            self.after(0, self.port_scan_button.configure, {"state": "normal"})
