# pages/browser_page.py
import customtkinter as ctk # Import the CustomTkinter library for modern-looking GUI widgets.
import tkinter as tk # Import the standard Tkinter library, though CustomTkinter is primary, some underlying Tkinter functionality might be used.
import logging # Import the logging module for recording events, debugging, and status messages.
from tkinterweb import HtmlFrame # Import HtmlFrame from tkinterweb, which provides an embedded web browser widget.

# Get a logger instance for this module. This allows for structured logging messages specific to the BrowserPage.
logger = logging.getLogger(__name__)

# --- Constants ---
# Define color constants to ensure consistent theming across the application, mimicking a "Pip-Boy" style.
PIPBOY_GREEN = "#32f178" # A distinct green color often associated with retro-futuristic interfaces like the Pip-Boy.
PIPBOY_FRAME = "#2a2d2e" # A dark grey color for background elements, providing contrast.

class BrowserPage(ctk.CTkFrame):
    """
    A page within a CustomTkinter application that embeds a simple web browser widget.
    This page allows users to input a URL and browse web content directly within the application.
    """
    def __init__(self, parent, controller):
        """
        Initializes the BrowserPage.

        Args:
            parent: The parent widget (e.g., the main application window or another frame)
                    to which this BrowserPage will be attached.
            controller: An instance of the main application controller, used to switch between pages.
        """
        # Call the constructor of the parent class (ctk.CTkFrame) to set up the frame itself.
        # Set a dark background color for the frame.
        super().__init__(parent, fg_color="#1a1a1a")
        self.controller = controller # Store a reference to the controller for navigation purposes.

        # --- Layout Configuration ---
        # Configure the grid layout for this frame.
        self.grid_columnconfigure(0, weight=1) # Make the first (and only) column expandable, so widgets stretch horizontally.
        self.grid_rowconfigure(2, weight=1) # Allow the third row (where the browser frame is placed) to expand vertically,
                                            # ensuring the browser takes up available space.

        # --- Header Section ---
        # Create a header frame to hold the page title and a back button.
        header = ctk.CTkFrame(self, fg_color="transparent") # Use a transparent background for the header frame.
        header.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew") # Place header at the top, spanning horizontally.
        header.columnconfigure(0, weight=1) # Make the first column in the header expandable for the title.

        # Add a label for the page title, styled with a specific font and color.
        ctk.CTkLabel(header, text="WEB BROWSER", font=("Arial", 20, "bold"), text_color=PIPBOY_GREEN).grid(row=0, column=0, sticky="w")
        # Add a button to navigate back to the home page.
        ctk.CTkButton(header, text="Back to Home", command=lambda: controller.show_page("HomePage")).grid(row=0, column=1, sticky="e", padx=10)

        # --- Navigation Bar Section ---
        # Create a frame for the URL entry and "Go" button.
        nav_frame = ctk.CTkFrame(self, fg_color=PIPBOY_FRAME) # Use the Pip-Boy frame color for the navigation bar background.
        nav_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew") # Place below header, spanning horizontally.
        nav_frame.grid_columnconfigure(1, weight=1) # Make the second column in the nav_frame expandable, allowing the URL entry to grow.

        # Create an entry widget for the user to type in URLs.
        self.url_entry = ctk.CTkEntry(nav_frame, placeholder_text="https://...", font=("Arial", 12))
        self.url_entry.grid(row=0, column=0, columnspan=2, padx=10, pady=5, sticky="ew") # Place entry, allowing it to span two columns.
        # Bind the <Return> key press event to the load_url_event method, so pressing Enter loads the URL.
        self.url_entry.bind("<Return>", self.load_url_event)

        # Create a button to manually trigger URL loading.
        self.go_button = ctk.CTkButton(nav_frame, text="Go", width=50, command=self.load_url)
        self.go_button.grid(row=0, column=2, padx=(0, 10), pady=5) # Place the "Go" button to the right of the URL entry.

        # --- Browser Frame ---
        # Initialize the HtmlFrame, which is the actual web browser component.
        # messages_enabled=False prevents the browser from logging its own internal messages to stdout.
        self.browser_frame = HtmlFrame(self, messages_enabled=False)
        self.browser_frame.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="nsew") # Place browser frame, making it expand in all directions.

        # Initialize a flag to ensure the default URL is loaded only once when the page is first shown.
        self.has_loaded_once = False

    def on_show(self):
        """
        This method is called by the application controller whenever this page is displayed.
        It's used to perform actions that should happen each time the page becomes visible,
        such as loading a default URL on the very first display.
        """
        # Check if the default URL has already been loaded.
        if not self.has_loaded_once:
            default_url = "https://www.google.com" # Define a default URL to load.
            self.url_entry.insert(0, default_url) # Insert the default URL into the entry box.
            self.load_url() # Call load_url to navigate to the default URL.
            self.has_loaded_once = True # Set the flag to true to prevent reloading on subsequent shows.
            logger.info("BrowserPage shown for the first time, loading default URL.") # Log the action.

    def load_url(self):
        """
        Retrieves the URL from the entry box, performs basic validation/sanitization,
        and then instructs the embedded browser to navigate to that URL.
        """
        url = self.url_entry.get().strip() # Get the text from the URL entry and remove leading/trailing whitespace.
        # Check if the URL starts with a protocol (http:// or https://).
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url # Prepend 'http://' if no protocol is specified, assuming HTTP by default.
            self.url_entry.delete(0, 'end') # Clear the entry box.
            self.url_entry.insert(0, url) # Re-insert the now-complete URL back into the entry box.
        
        logger.info(f"Attempting to load URL: {url}") # Log the URL that is about to be loaded.
        self.browser_frame.load_url(url) # Instruct the HtmlFrame to load the specified URL.

    def load_url_event(self, event=None):
        """
        An event handler method specifically designed to be triggered when the <Return> (Enter)
        key is pressed in the URL entry field.
        
        Args:
            event: The event object (optional, passed by Tkinter when binding to events).
        """
        self.load_url() # Call the main load_url method to process and load the URL.