# pages/vehicle_page.py
# This page provides an interface for connecting to a vehicle's On-Board Diagnostics (OBD-II) system,
# displaying real-time vehicle data (gauges), and performing diagnostic actions like reading
# and clearing Diagnostic Trouble Codes (DTCs). It's designed to be modular and resilient
# to the absence of required external libraries (python-obd, pyserial).

# --- Standard Library Imports ---
import customtkinter as ctk  # GUI framework for creating modern-looking Tkinter widgets.
import tkinter as tk         # Standard Python GUI library (specifically used for `messagebox`).
from tkinter import messagebox # Specific module for displaying standard GUI pop-up messages (e.g., error, warning).
import logging               # For logging events, warnings, and errors throughout the module.
import threading             # For running time-consuming operations (like connecting to OBD) in the background
                             # to prevent the GUI from freezing.
import time                  # For adding delays (e.g., during connection attempts and polling).
from typing import Optional, Dict, List, Any, Tuple # For type hinting, which improves code readability,
                                                # maintainability, and allows for static analysis.

# --- Conditional Library Imports ---
# These blocks attempt to import external libraries crucial for OBD-II functionality.
# If a library is not found, a mock class or specific functionality is disabled,
# and a warning is logged. This ensures the application can still run, albeit with limited features.

OBD_AVAILABLE = False # A flag to indicate if the 'python-obd' library was successfully imported.
try:
    import obd # The primary library for interacting with OBD-II adapters and reading vehicle data.
    OBD_AVAILABLE = True
    # Suppress excessive logging from the obd library itself to keep application logs cleaner.
    # We only want to see warnings and errors from the obd library.
    obd.logger.setLevel(obd.logging.WARNING)
except (ImportError, ModuleNotFoundError):
    # If `python-obd` is not found, we create a mock `obd` class structure.
    # This prevents `NameError` if `obd` is referenced later and allows the UI to still
    # initialize and display a message about the missing functionality.
    class obd:
        class OBD: pass # Mock for the main OBD class
        class Async: # Mock for the asynchronous OBD connection class
            def __init__(self, *args: Any, **kwargs: Any) -> None: pass
            def start(self) -> None: pass
            def stop(self) -> None: pass
            def close(self) -> None: pass
            def is_connected(self) -> bool: return False # Always returns False if mock
            def watch(self, command: Any, callback: Any) -> None: pass # Mock method
            def supports(self, command: Any) -> bool: return False # Always returns False if mock
            # Mock query method that returns a null response
            def query(self, command: Any, force: bool = False) -> 'obd.OBDResponse': return obd.OBDResponse() # Add force kwarg
        class commands: # Mock for common OBD commands
            # All commands are mocked to None, so they cannot be used.
            RPM, SPEED, INTAKE_PRESSURE, COOLANT_TEMP, RUN_TIME, THROTTLE_POS, GET_DTC, CLEAR_DTC = (None,) * 8
        
        class OBDResponse: # Mock for an OBD command response
            def is_null(self) -> bool: return True # Always null for the mock
            @property
            def value(self): # Mock for the response value with a magnitude property
                class MockUnit:
                    magnitude = None
                    def to(self, unit_name: str): return self # Allows chaining like .to('mph')
                return MockUnit()
    # Log a warning to inform the user that OBD functionality is limited.
    logging.getLogger(__name__).warning("python-obd library not found. Vehicle page will have limited functionality.")

SERIAL_AVAILABLE = False # A flag to indicate if the 'pyserial' library was successfully imported.
try:
    import serial.tools.list_ports # Used to scan for available serial (USB-to-serial) ports.
    SERIAL_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    # Log a warning if pyserial is not found, as port scanning won't work.
    logging.getLogger(__name__).warning("pyserial library not found. Port scanning will be disabled.")


logger = logging.getLogger(__name__) # Get a logger instance for this module, using its name.

# --- UI Constants ---
# Define color schemes and fonts consistent with a "Pipboy" (Fallout-style) theme.
PIPBOY_GREEN = "#32f178"
PIPBOY_FRAME = "#2a2d2e"
MAIN_BG_COLOR = "#1a1a1a"
GAUGE_FONT_LARGE = ("Arial", 48, "bold") # Font for large gauge values
GAUGE_FONT_SMALL = ("Arial", 12) # Font for gauge descriptions/units
ERROR_COLOR = "#FF5500" # A distinct color for error messages or critical buttons.

# --- Connection Parameters ---
CONNECTION_TIMEOUT_SECONDS = 15 # Maximum time to wait for an OBD-II adapter connection to establish.
                                # Increased slightly to accommodate slower or older adapters.

# --- GaugeWidget Helper Class ---
class GaugeWidget(ctk.CTkFrame):
    """
    A reusable CustomTkinter widget designed to display a single vehicle statistic.
    It features a large, prominent label for the numerical value and a smaller label
    below it for the description and units, styled with the Pipboy theme.
    """
    def __init__(self, parent: ctk.CTkFrame, label_text: str, unit_text: str) -> None:
        """
        Initializes a new GaugeWidget.

        Args:
            parent: The CTkFrame widget that will contain this gauge.
            label_text: The main descriptive label for the gauge (e.g., "Engine", "Speed").
            unit_text: The units for the displayed value (e.g., "RPM", "KPH").
        """
        super().__init__(parent, fg_color=PIPBOY_FRAME, corner_radius=8)
        self.grid_columnconfigure(0, weight=1) # Make the single column expandable
        
        # Label for displaying the actual vehicle data value.
        self.value_label = ctk.CTkLabel(self, text="--", font=GAUGE_FONT_LARGE, text_color=PIPBOY_GREEN)
        self.value_label.grid(row=0, column=0, sticky="s", padx=10, pady=(10, 0)) # Sticky 's' aligns to bottom
        
        # Combine the descriptive label and unit for the bottom text.
        full_label_text = f"{label_text} ({unit_text})"
        self.description_label = ctk.CTkLabel(self, text=full_label_text, font=GAUGE_FONT_SMALL)
        self.description_label.grid(row=1, column=0, sticky="n", padx=10, pady=(0, 10)) # Sticky 'n' aligns to top

    def update_value(self, value: Optional[Any]) -> None:
        """
        Updates the displayed value on the gauge.
        It handles different input types (None, string, numeric) and formats them appropriately.

        Args:
            value: The new value to display. Can be None, a string, or a number.
        """
        if value is None:
            display_text = "--" # Default text if value is None
            color = "gray"     # Grey color for no value
        elif isinstance(value, str):
            display_text = value # Use string directly if already formatted
            color = PIPBOY_GREEN # Pipboy green for valid strings
        else:
            try:
                val_float = float(value) # Attempt to convert to float for formatting
                # Format as integer if it's a whole number, otherwise one decimal place.
                display_text = f"{val_float:.0f}" if val_float == int(val_float) else f"{val_float:.1f}"
                color = PIPBOY_GREEN
            except (ValueError, TypeError):
                display_text = "N/A" # If conversion fails
                color = "gray"
        
        # Configure the label with the new text and color.
        self.value_label.configure(text=display_text, text_color=color)

# --- Main Vehicle Page Class ---
class VehiclePage(ctk.CTkFrame):
    """
    A modular CustomTkinter page designed for vehicle interaction via OBD-II.
    It provides UI for:
    - Scanning and selecting serial ports for OBD-II adapters.
    - Connecting and disconnecting from the vehicle.
    - Dynamically displaying real-time data through gauges based on supported commands.
    - Reading and clearing Diagnostic Trouble Codes (DTCs).
    """
    def __init__(self, parent: ctk.CTkBaseClass, controller: Any) -> None:
        """
        Initializes the VehiclePage.

        Args:
            parent: The CTkBaseClass (container) that this page will be placed in.
            controller: A reference to the main application controller, used for page navigation
                        and potentially for AI service hub requests.
        """
        super().__init__(parent, fg_color=MAIN_BG_COLOR)
        self.controller = controller # Store the controller reference

        # Central configuration list for all potential vehicle data gauges.
        # Each dictionary defines an OBD command, its internal name, UI label,
        # unit, and an optional conversion unit (e.g., Celsius to Fahrenheit).
        self.SUPPORTED_COMMANDS = [
            {"cmd": obd.commands.RPM, "name": "RPM", "label": "Engine", "unit": "RPM", "convert_to": None},
            {"cmd": obd.commands.SPEED, "name": "SPEED", "label": "Speed", "unit": "KPH", "convert_to": "mph"},
            {"cmd": obd.commands.INTAKE_PRESSURE, "name": "BOOST_PRESSURE", "label": "Intake", "unit": "kPa", "convert_to": "psi"},
            {"cmd": obd.commands.COOLANT_TEMP, "name": "COOLANT_TEMP", "label": "Coolant", "unit": "°C", "convert_to": "fahrenheit"},
            {"cmd": obd.commands.RUN_TIME, "name": "RUN_TIME", "label": "Run Time", "unit": "seconds", "convert_to": None},
            {"cmd": obd.commands.THROTTLE_POS, "name": "THROTTLE_POS", "label": "Throttle", "unit": "%", "convert_to": None},
        ]

        # --- Connection State Variables ---
        self.connection: Optional[obd.Async] = None # The `python-obd` asynchronous connection object.
        self.is_connected = False # Flag indicating if an active OBD connection is established.
        self.is_connecting = False # Flag indicating if a connection attempt is currently in progress.
        self.is_reading_dtcs = False # Flag indicating if DTC reading is in progress.
        self.is_clearing_dtcs = False # Flag indicating if DTC clearing is in progress.
        
        self.gauges: Dict[str, GaugeWidget] = {} # Dictionary to store active GaugeWidget instances, by command name.
        self.available_ports: List[str] = [] # List of discovered serial port names.

        # Configure the grid layout for the main page.
        self.grid_columnconfigure(0, weight=1) # Make the main column expandable.
        self.grid_rowconfigure(1, weight=1)   # Make the tab view row expandable.

        # --- Header Frame ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=10, pady=(10,0), sticky="ew")
        header.grid_columnconfigure(0, weight=1) # Make the title column expandable.
        
        # Page title label.
        ctk.CTkLabel(header, text="VEHICLE INTERFACE", font=("Arial", 24, "bold"), text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w")
        # Button to navigate back to the Home page.
        ctk.CTkButton(header, text="Back to Home", command=lambda: controller.show_page("HomePage")).grid(row=0, column=1, sticky="e")

        # --- Tab View for Gauges/Status and Diagnostics ---
        self.tab_view = ctk.CTkTabview(self, fg_color=PIPBOY_FRAME)
        self.tab_view.add("Gauges & Status") # First tab for real-time data and connection status.
        self.tab_view.add("Diagnostics")    # Second tab for DTC reading and clearing.
        self.tab_view.grid(row=1, column=0, sticky="nsew", padx=10, pady=10) # Position the tab view.

        # Setup the content for each tab.
        self._setup_gauges_tab()
        self._setup_diagnostics_tab()
        
        # Initial UI state update.
        self._update_ui_state() 

    def _setup_gauges_tab(self) -> None:
        """
        Configures the "Gauges & Status" tab with connection controls,
        status display, and a container for dynamic gauges.
        """
        tab = self.tab_view.tab("Gauges & Status")
        tab.grid_columnconfigure(0, weight=1) # Make the content column expandable.
        tab.grid_rowconfigure(2, weight=1)   # Make the gauge container row expandable.

        # --- Connection Controls Frame ---
        connection_frame = ctk.CTkFrame(tab, fg_color="transparent")
        connection_frame.grid(row=0, column=0, pady=10, sticky="ew")
        connection_frame.grid_columnconfigure(1, weight=1) # Make the dropdown column expandable.

        self.scan_ports_button = ctk.CTkButton(connection_frame, text="Scan Ports", width=100, command=self.scan_for_ports)
        self.scan_ports_button.grid(row=0, column=0, padx=(0, 5))

        self.port_dropdown_var = ctk.StringVar(value="No ports found...") # Variable to hold selected port text.
        self.port_dropdown = ctk.CTkOptionMenu(connection_frame, variable=self.port_dropdown_var, values=[])
        self.port_dropdown.grid(row=0, column=1, padx=5, sticky="ew")

        self.connect_button = ctk.CTkButton(connection_frame, text="Connect", width=100, command=self.connect_to_obd)
        self.connect_button.grid(row=0, column=2, padx=(5, 0))

        # Disconnect button is initially hidden and configured with an error-like color.
        self.disconnect_button = ctk.CTkButton(connection_frame, text="Disconnect", width=100, fg_color=ERROR_COLOR, hover_color="#b33c00", command=self.disconnect_from_obd)
        # It's not gridded here; its visibility is managed by `_update_ui_state`.

        # --- Status Display Frame ---
        status_frame = ctk.CTkFrame(tab, fg_color="transparent")
        status_frame.grid(row=1, column=0, pady=(0, 10))
        self.status_label = ctk.CTkLabel(status_frame, text="Status: INITIALIZING", text_color="orange")
        self.status_label.pack()

        # --- Gauge Container Frame (Scrollable) ---
        # This frame will hold the dynamically created GaugeWidget instances.
        self.gauge_container_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.gauge_container_frame.grid(row=2, column=0, sticky="nsew")
        self.gauge_container_frame.grid_columnconfigure((0, 1, 2), weight=1) # Allow up to 3 columns for gauges.
        
    def _setup_diagnostics_tab(self) -> None:
        """
        Configures the "Diagnostics" tab with buttons for reading and clearing DTCs
        and a text box to display the results.
        """
        tab = self.tab_view.tab("Diagnostics")
        tab.grid_columnconfigure(0, weight=1) # Make the content column expandable.
        tab.grid_rowconfigure(1, weight=1)   # Make the textbox row expandable.

        # --- Controls Frame for Diagnostic Actions ---
        controls_frame = ctk.CTkFrame(tab, fg_color="transparent")
        controls_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        controls_frame.grid_columnconfigure((0, 1), weight=1) # Two equally weighted columns for buttons.

        self.read_dtc_button = ctk.CTkButton(controls_frame, text="Read Trouble Codes (DTCs)", command=self.read_dtcs)
        self.read_dtc_button.grid(row=0, column=0, padx=5, sticky="ew")
        
        # Clear DTC button with a warning color.
        self.clear_dtc_button = ctk.CTkButton(controls_frame, text="Clear Trouble Codes & Check Engine Light", command=self.clear_dtcs, fg_color=ERROR_COLOR, hover_color="#b33c00")
        self.clear_dtc_button.grid(row=0, column=1, padx=5, sticky="ew")

        # --- DTC Results Textbox ---
        self.dtc_results_text = ctk.CTkTextbox(tab, font=("Arial", 12), wrap="word", state="disabled")
        self.dtc_results_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def on_show(self) -> None:
        """
        Lifecycle method called when this page is displayed.
        It initiates a scan for serial ports if the necessary libraries are available.
        """
        if OBD_AVAILABLE and SERIAL_AVAILABLE:
            self.scan_for_ports()

    def on_hide(self) -> None:
        """
        Lifecycle method called when this page is hidden or the application closes.
        Ensures the OBD-II connection is properly disconnected to release resources.
        """
        self.disconnect_from_obd()

    def _update_ui_state(self) -> None:
        """
        Updates the visibility and enabled/disabled state of various UI elements
        based on the current connection status (connected, connecting, disconnected, or library missing).
        """
        # --- Handle Missing Libraries State ---
        if not OBD_AVAILABLE or not SERIAL_AVAILABLE:
            lib_missing_msg = []
            if not OBD_AVAILABLE: lib_missing_msg.append("python-obd")
            if not SERIAL_AVAILABLE: lib_missing_msg.append("pyserial")
            # Display a clear status message about missing libraries.
            self.status_label.configure(text=f"Status: LIBRARIES MISSING ({', '.join(lib_missing_msg).upper()})", text_color=ERROR_COLOR)
            # Disable all interactive elements if libraries are missing.
            for btn in [self.scan_ports_button, self.port_dropdown, self.connect_button, self.read_dtc_button, self.clear_dtc_button]:
                btn.configure(state="disabled")
            self.disconnect_button.grid_remove() # Ensure disconnect button is hidden.
            return

        # --- Handle Connected State ---
        if self.is_connected:
            self.status_label.configure(text="Status: CONNECTED", text_color=PIPBOY_GREEN)
            self.scan_ports_button.configure(state="disabled") # Cannot scan/change port while connected.
            self.port_dropdown.configure(state="disabled")
            self.connect_button.grid_remove() # Hide connect button.
            self.disconnect_button.grid(row=0, column=2, padx=(5, 0)) # Show disconnect button.
            # Disable diagnostic buttons if a diagnostic operation is already in progress.
            is_diag_running = self.is_reading_dtcs or self.is_clearing_dtcs
            self.read_dtc_button.configure(state="disabled" if is_diag_running else "normal") 
            self.clear_dtc_button.configure(state="disabled" if is_diag_running else "normal")
        # --- Handle Connecting State ---
        elif self.is_connecting:
            self.status_label.configure(text="Status: CONNECTING...", text_color="yellow")
            # Disable all control buttons during connection attempt.
            for btn in [self.scan_ports_button, self.port_dropdown, self.connect_button, self.read_dtc_button, self.clear_dtc_button]:
                btn.configure(state="disabled")
            self.disconnect_button.grid_remove()
        # --- Handle Disconnected State ---
        else: # Disconnected state
            self.status_label.configure(text="Status: DISCONNECTED", text_color="orange")
            self.scan_ports_button.configure(state="normal") # Enable scanning.
            self.port_dropdown.configure(state="normal")     # Enable port selection.
            self.disconnect_button.grid_remove()             # Hide disconnect button.
            self.connect_button.grid(row=0, column=2, padx=(5, 0)) # Show connect button.
            # Enable connect button only if ports were found.
            self.connect_button.configure(state="normal" if self.available_ports else "disabled")
            self.read_dtc_button.configure(state="disabled")  # Disable diagnostic buttons when disconnected.
            self.clear_dtc_button.configure(state="disabled")

    def scan_for_ports(self) -> None:
        """
        Scans for available serial ports (specifically focusing on common USB-to-serial adapters
        like those with 'ttyUSB' or 'ttyACM' in their name on Linux/Raspberry Pi).
        Updates the port dropdown menu with the discovered ports.
        """
        if not SERIAL_AVAILABLE:
            messagebox.showerror("Error", "pyserial library is not installed.", parent=self)
            return
        logger.info("Scanning for serial ports...")
        # Use pyserial's list_ports to find available serial devices.
        # Filter for typical Raspberry Pi serial device names.
        ports = [p.device for p in serial.tools.list_ports.comports() if 'ttyUSB' in p.name or 'ttyACM' in p.name]
        self.available_ports = ports
        if ports:
            self.port_dropdown.configure(values=ports) # Update dropdown with found ports.
            self.port_dropdown_var.set(ports[0])      # Select the first port by default.
        else:
            self.port_dropdown.configure(values=["No ports found..."]) # Indicate no ports found.
            self.port_dropdown_var.set("No ports found...")
        self._update_ui_state() # Update UI element states.

    def connect_to_obd(self) -> None:
        """
        Initiates an asynchronous connection to the OBD-II adapter using the selected serial port.
        This operation is offloaded to a separate thread to keep the GUI responsive.
        """
        selected_port = self.port_dropdown_var.get()
        if not selected_port or "No ports" in selected_port:
            messagebox.showerror("Error", "No valid port selected.", parent=self)
            return
        if self.is_connecting or self.is_connected: return # Prevent multiple connection attempts.
        
        self.is_connecting = True
        self._update_ui_state() # Update UI to show "Connecting..." state.
        # Start a new thread for the connection process. `daemon=True` ensures the thread
        # will terminate automatically when the main application exits.
        threading.Thread(target=self._obd_connection_thread, args=(selected_port,), daemon=True).start()

    def disconnect_from_obd(self) -> None:
        """
        Gracefully disconnects from the OBD-II adapter, stops the `python-obd` connection,
        clears all dynamic gauges, and resets the connection state variables.
        """
        if self.connection:
            logger.info("Disconnecting from OBD-II adapter.")
            if self.connection.is_connected():
                self.connection.stop() # Stop the asynchronous reader.
            self.connection.close() # Close the serial port.
        self.connection = None # Clear the connection object.
        self.is_connected = False
        self.is_connecting = False
        self._clear_all_gauges() # Remove all dynamically created gauges.
        self._update_ui_state() # Update UI to disconnected state.

    def _obd_connection_thread(self, port: str) -> None:
        """
        The actual logic for connecting to the OBD-II adapter, run in a background thread.
        It attempts to connect, waits for connection, and then sets up dynamic gauges.

        Args:
            port: The serial port string (e.g., "/dev/ttyUSB0") to connect to.
        """
        try:
            # Initialize an asynchronous OBD connection. `fast=False` might improve compatibility.
            self.connection = obd.Async(portstr=port, fast=False)
            self.connection.start() # Start the connection process in its own internal thread.
            
            start_time = time.time()
            # Wait loop for the connection to be established, with a timeout.
            while not self.connection.is_connected():
                if time.time() - start_time > CONNECTION_TIMEOUT_SECONDS:
                    raise ConnectionError(f"Connection timed out after {CONNECTION_TIMEOUT_SECONDS} seconds.")
                time.sleep(0.1) # Short delay to prevent busy-waiting.
            
            self.is_connected = True
            self.is_connecting = False
            # Schedule UI updates back on the main Tkinter thread using `self.after(0, ...)`.
            # This is crucial for safely modifying GUI elements from a background thread.
            self.after(0, self._update_ui_state)
            logger.info("OBD-II connection established. Discovering supported commands...")
            self.after(0, self._create_dynamic_gauges) # Create gauges based on supported commands.
        except Exception as e:
            logger.error(f"OBD-II connection failed: {e}", exc_info=True)
            # Display error message and reset UI state on connection failure.
            self.after(0, lambda: messagebox.showerror("Connection Error", f"Connection Failed: {e}", parent=self))
            self.after(0, self.disconnect_from_obd)

    def _create_dynamic_gauges(self) -> None:
        """
        After a successful connection, this method determines which OBD commands
        are supported by the connected vehicle and dynamically creates `GaugeWidget`s
        for each supported command. It then sets up `obd.Async` watchers for these commands.
        """
        if not self.connection: return # Ensure connection object exists.
        
        max_cols, row, col = 3, 0, 0 # Layout parameters for gauges (up to 3 columns).
        for command_info in self.SUPPORTED_COMMANDS:
            cmd_obj = command_info["cmd"]
            if not cmd_obj: continue # Skip if command object is None (e.g., due to mock obd).
            
            # Check if the connected vehicle supports this specific OBD command.
            if self.connection.supports(cmd_obj):
                cmd_name = command_info["name"]
                logger.info(f"Vehicle supports {cmd_name}. Creating gauge.")
                # Determine the unit label for the gauge (either original or converted).
                unit_label = command_info["convert_to"].upper() if command_info["convert_to"] else command_info["unit"]
                gauge = GaugeWidget(self.gauge_container_frame, command_info["label"], unit_label)
                # Position the gauge in the grid.
                gauge.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                self.gauges[cmd_name] = gauge # Store the gauge instance.
                
                # Create a callback function specific to this gauge and command.
                callback = self._create_gauge_callback(cmd_name, command_info.get("convert_to"))
                # Register the callback with `obd.Async` to automatically update the gauge
                # whenever new data for this command is received.
                self.connection.watch(cmd_obj, callback=callback)
                
                # Advance grid position for the next gauge.
                col += 1
                if col >= max_cols: col, row = 0, row + 1
            else:
                logger.warning(f"Vehicle does not support {command_info['name']}. Skipping gauge.")

    def _create_gauge_callback(self, gauge_name: str, convert_to: Optional[str]) -> Any:
        """
        A factory function that generates a callback for `obd.Async.watch`.
        This callback updates a specific `GaugeWidget` with the latest data.

        Args:
            gauge_name: The name of the gauge (key in `self.gauges`) to update.
            convert_to: Optional unit to convert the value to (e.g., 'mph', 'fahrenheit').

        Returns:
            A callable function that takes an `obd.OBDResponse` and updates the GUI.
        """
        def callback(response: obd.OBDResponse) -> None:
            if not response.is_null(): # Check if the response contains valid data.
                value_obj = response.value # Get the raw value object from the response.
                if convert_to:
                    # If unit conversion is specified, perform it.
                    # `obd.Unit` objects have a `.to()` method.
                    value_obj = value_obj.to(convert_to)
                
                # Special handling for RUN_TIME to format it as HH:MM:SS.
                if gauge_name == "RUN_TIME":
                    seconds = int(value_obj.magnitude) # Get the numeric value.
                    m, s = divmod(seconds, 60) # Convert seconds to minutes and remaining seconds.
                    h, m = divmod(m, 60)     # Convert minutes to hours and remaining minutes.
                    # Schedule the UI update on the main thread with the formatted time string.
                    self.after(0, self.gauges[gauge_name].update_value, f"{h:02d}:{m:02d}:{s:02d}")
                else:
                    # For other gauges, update with the numeric magnitude.
                    self.after(0, self.gauges[gauge_name].update_value, value_obj.magnitude)
        return callback
        
    def _clear_all_gauges(self) -> None:
        """
        Removes all dynamically created `GaugeWidget` instances from the `gauge_container_frame`.
        """
        for widget in self.gauge_container_frame.winfo_children():
            widget.destroy() # Destroy each child widget.
        self.gauges.clear() # Clear the dictionary of gauge references.

    def read_dtcs(self) -> None:
        """
        Initiates the process of reading Diagnostic Trouble Codes from the vehicle ECU.
        Checks for connection and prevents multiple concurrent readings.
        """
        if not self.is_connected:
            messagebox.showerror("Not Connected", "Please connect to the vehicle first.", parent=self)
            return
        if self.is_reading_dtcs: return # Prevent re-triggering if already reading.
        self.is_reading_dtcs = True
        self._update_ui_state() # Update UI to reflect reading in progress (e.g., disable buttons).
        threading.Thread(target=self._read_dtcs_thread, daemon=True).start() # Run in background.

    def _read_dtcs_thread(self) -> None:
        """
        Background thread logic for querying the vehicle for DTCs.
        It updates the diagnostic textbox with progress and results.
        """
        try:
            # Clear previous results and show initial status message in the textbox.
            self.after(0, self._update_dtc_textbox, "normal", "1.0", "Querying ECU for trouble codes...\n")
            self.after(0, self._update_dtc_textbox, "end", "Checking if command is supported by the vehicle...\n")

            # Check if the vehicle explicitly supports the GET_DTC command.
            if not self.connection.supports(obd.commands.GET_DTC):
                self.after(0, lambda: messagebox.showwarning("Not Supported", "Vehicle does not support reading DTCs.", parent=self))
                self.after(0, self._update_dtc_textbox, "end", "\n[WARNING] Vehicle ECU does not support reading DTCs.\n")
                return

            self.after(0, self._update_dtc_textbox, "end", "Support confirmed. Sending query to ECU...\n")
            # Query the ECU for DTCs. `force=True` ensures the command is sent even if cached.
            response = self.connection.query(obd.commands.GET_DTC, force=True)
            
            if response.is_null() or not response.value:
                # If response is null or empty, no codes were found.
                self.after(0, self._update_dtc_textbox, "end", "\n[SUCCESS] No trouble codes found.")
            else:
                self.after(0, self._update_dtc_textbox, "end", "\n--- Found Trouble Codes ---\n")
                # Iterate through found codes and descriptions, displaying each.
                for code, desc in response.value:
                    self.after(0, self._update_dtc_textbox, "end", f"- {code}: {desc}\n")
        except Exception as e:
            logger.error(f"Error reading DTCs: {e}", exc_info=True)
            self.after(0, self._update_dtc_textbox, "end", f"\n[ERROR] Failed to read DTCs: {e}")
        finally:
            self.is_reading_dtcs = False # Reset flag.
            self.after(0, self._update_dtc_textbox, "state", "disabled") # Disable textbox editing.
            self.after(0, self._update_ui_state) # Update UI (e.g., re-enable buttons).

    def clear_dtcs(self) -> None:
        """
        Initiates the process of clearing Diagnostic Trouble Codes from the vehicle ECU.
        Includes a confirmation dialog before proceeding.
        """
        if not self.is_connected:
            messagebox.showerror("Not Connected", "Please connect to the vehicle first.", parent=self)
            return
        if self.is_clearing_dtcs: return # Prevent re-triggering.
        # Ask for user confirmation before performing a potentially irreversible action.
        if not messagebox.askyesno("Confirm Action", "This will clear all DTCs and turn off the Check Engine Light.\nAre you sure you want to proceed?", parent=self): return
        
        self.is_clearing_dtcs = True
        self._update_ui_state() # Update UI to reflect clearing in progress.
        threading.Thread(target=self._clear_dtcs_thread, daemon=True).start() # Run in background.

    def _clear_dtcs_thread(self) -> None:
        """
        Background thread logic for sending the clear DTCs command to the vehicle.
        It updates the diagnostic textbox with progress and results.
        """
        try:
            self.after(0, self._update_dtc_textbox, "normal", "1.0", "Sending command to clear codes...\n")
            self.after(0, self._update_dtc_textbox, "end", "Checking if command is supported by the vehicle...\n")

            # Check if the vehicle explicitly supports the CLEAR_DTC command.
            if not self.connection.supports(obd.commands.CLEAR_DTC):
                self.after(0, lambda: messagebox.showwarning("Not Supported", "Vehicle does not support clearing DTCs.", parent=self))
                self.after(0, self._update_dtc_textbox, "end", "\n[WARNING] Vehicle ECU does not support clearing DTCs.\n")
                return

            self.after(0, self._update_dtc_textbox, "end", "Support confirmed. Sending clear command to ECU...\n")
            # Send the clear DTC command. `force=True` ensures it's sent.
            response = self.connection.query(obd.commands.CLEAR_DTC, force=True)

            # A non-null response with a non-None value typically indicates success for clear commands.
            if not response.is_null() and response.value is not None: 
                self.after(0, self._update_dtc_textbox, "end", "\n[SUCCESS] Clear DTC command sent successfully.")
            else:
                self.after(0, self._update_dtc_textbox, "end", "\n[WARNING] ECU did not respond as expected. Codes may not be cleared.")
        except Exception as e:
            logger.error(f"Error clearing DTCs: {e}", exc_info=True)
            self.after(0, self._update_dtc_textbox, "end", f"\n[ERROR] Failed to clear DTCs: {e}")
        finally:
            self.is_clearing_dtcs = False # Reset flag.
            self.after(0, self._update_dtc_textbox, "state", "disabled") # Disable textbox editing.
            self.after(0, self._update_ui_state) # Update UI.

    def _update_dtc_textbox(self, command: str, index: str, text: str = "") -> None:
        """
        Safely updates the `dtc_results_text` CustomTkinter Textbox from any thread.
        This method is designed to be called via `self.after(0, ...)` to ensure
        GUI updates happen on the main thread.

        Args:
            command: "normal" to enable, clear, and insert; "end" to append; "state" to change state.
            index: The starting index for operations (e.g., "1.0" for beginning, "end" for end).
            text: The text to insert or append (if applicable).
        """
        # Check if the textbox widget still exists (e.g., page might have been hidden/destroyed).
        if not self.dtc_results_text.winfo_exists(): return
        
        if command == "normal":
            self.dtc_results_text.configure(state="normal") # Enable editing.
            self.dtc_results_text.delete(index, "end")     # Clear existing text.
            self.dtc_results_text.insert(index, text)      # Insert new text.
        elif command == "end":
            self.dtc_results_text.configure(state="normal") # Enable editing to append.
            self.dtc_results_text.insert(index, text)       # Insert text at the end.
        elif command == "state":
            self.dtc_results_text.configure(state=index) # Change the textbox state (e.g., "disabled").