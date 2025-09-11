import time
import snappi
import urllib3
import tkinter as tk
from tkinter import ttk
import threading
import urllib.parse
import argparse
import logging


#########################################################################
# Parse command line arguments for debug mode

parser = argparse.ArgumentParser(description='IXIA Traffic Control GUI')
parser.add_argument('-d', '--debug', action='store_true', help='Enable debug logging')
args = parser.parse_args()

# Configure logging based on debug flag
log_level = logging.DEBUG if args.debug else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Create logger for this module
logger = logging.getLogger(__name__)

#########################################################################
# Import configuration for MAC and IP addresses from 'config' module

from config.b5g import (SRC_MAC, DST_MAC, SRC_IP, DST_IPS, IXIA_API_LOCATION, NCS_API_LOCATION,
                    R1_MAC, R2_MAC, R1_IP, R2_IP, R1_GATEWAY, R2_GATEWAY, IP_PREFIX)

#########################################################################


urllib3.disable_warnings()

src_mac = SRC_MAC
dst_mac = DST_MAC
src_ip = SRC_IP
dst_ips = DST_IPS

# Create a new API handle to make API calls against OTG
# with HTTP as default transport protocol
api = snappi.api(location=IXIA_API_LOCATION)


# Create a new traffic configuration that will be set on OTG
cfg = api.config()

# Add tx and rx ports to the configuration
ptx = cfg.ports.add(name="ptx", location="eth1")
prx = cfg.ports.add(name="prx", location="eth2")

# Limit link speed to 100 Mbps full-duplex
# link100 = cfg.layer1.add(name="link100", port_names=["ptx", "prx"])
# link100.speed = "speed_100_fd_mbps"

# Add two devices to the configuration
# and set their MAC addresses
r1 = cfg.devices.add(name="r1")
r2 = cfg.devices.add(name="r2")

r1Eth = r1.ethernets.add(name="r1Eth")
r1Eth.mac = R1_MAC

r2Eth = r2.ethernets.add(name="r2Eth")
r2Eth.mac = R2_MAC

# Set connection of each device to the corresponding test port
r1Eth.connection.port_name = ptx.name
r2Eth.connection.port_name = prx.name

# Add IPv6 addresses to each device
r1Ip = r1Eth.ipv6_addresses.add(name="r1Ip", address=R1_IP, gateway=R1_GATEWAY, prefix=IP_PREFIX)
r2Ip = r2Eth.ipv6_addresses.add(name="r2Ip", address=R2_IP, gateway=R2_GATEWAY, prefix=IP_PREFIX)


#########################################################################
# Import 'BUTTON_VARIANT', 'flow_definition' function and 'variation_function' (if available) from 'flow_definitions' module

#from flow_definitions.fixed_packet_size_fixed_rate_mbps_continuous import define_flow, BUTTON_VARIANT
from flow_definitions.fixed_packet_size_fixed_rate_mbps_interval import define_flow, BUTTON_VARIANT, variation_function
import requests

from minio_flow_uploader import create_initial_flows_file, monitor_s3_files, log_current_stack


#########################################################################
# Create flows via define_flow function

packet_size = 669
#flow_rate = 10  # Mbps
flow_rate = 8

for dst_ip in dst_ips:
    define_flow(cfg, f"flow_{dst_ip}", r1Ip, r2Ip, packet_size, flow_rate, src_ip, dst_ip, src_mac, dst_mac)


# Define 'variation_interval' if 'variation_function' is available
variation_interval = 60

# Define 'simultaneous_flows' if 'variation_function' is available
simultaneous_flows = [7,6,5,4,3,4,5,6,7,8,8,8,8,8,8,8,8,9,9,9,10,10,9,8,0]

# Define variation function if available
variation_thread = None
variation_stop_event = None
variation_running = False

def gui_variation_function():
    global variation_thread, variation_stop_event, variation_running
    logger.debug(f"gui_variation_function llamada - variation_running: {variation_running}")
    if not variation_running:
        logger.debug("Entrando en create_initial_flows_file...")
        create_initial_flows_file(dst_ips[:simultaneous_flows[0]])
        logger.debug("create_initial_flows_file completado")
        
        variation_running = True
        # Disable start button
        if 'start' in gui.flow_buttons:
            gui.flow_buttons['start'].configure(state='disabled', text="Variation Running...")
        variation_thread, variation_stop_event = variation_function(api, cfg, NCS_API_LOCATION, variation_interval, simultaneous_flows)


#########################################################################

# Push traffic configuration constructed so far to OTG
api.set_config(cfg)

# Start transmitting the packets from configured flow
cs = api.control_state()

def get_configured_flows(cfg):
    """Get information about configured flows"""
    flows = []
    for flow in cfg.flows:
        # Get IPv6 destination from the raw configuration
        # since packet fields are not accessible after flow creation
        flows.append({
            'name': flow.name,
            'rate': flow.rate.mbps,
            'dst_ip': flow.name.replace('flow_', '')  # Extract from flow name since we used dst_ip in name
        })
    return flows

# Get configured flows before GUI creation
configured_flows = get_configured_flows(cfg)

class TrafficControlGUI:
    def __init__(self, api, cs, flows, button_variant="individual", variation_function=None):
        self.root = tk.Tk()
        self.root.title("Traffic Flow Control")
        self.button_variant = button_variant
        self.root.geometry("1200x800")
        self.api = api
        self.cs = cs
        self.flows = flows
        self.flow_states = {i+1: False for i in range(len(flows))}
        
        # Configure root window to be resizable
        self.root.columnconfigure(1, weight=1)  # Changed to 1 since buttons are in column 0
        self.root.rowconfigure(0, weight=1)
        
        # Create scrollable button frame
        button_container = ttk.Frame(self.root)
        button_container.grid(row=0, column=0, sticky='ns', padx=5, pady=5)
        
        # Create canvas and scrollbar for buttons
        button_canvas = tk.Canvas(button_container, width=200)
        button_scrollbar = ttk.Scrollbar(button_container, orient="vertical", command=button_canvas.yview)
        
        # Create frame for buttons inside canvas
        button_frame = ttk.Frame(button_canvas)
        button_frame.bind("<Configure>", 
            lambda e: button_canvas.configure(scrollregion=button_canvas.bbox("all")))
        
        # Add button frame to canvas
        button_canvas.create_window((0, 0), window=button_frame, anchor="nw")
        button_canvas.configure(yscrollcommand=button_scrollbar.set)
        
        # Pack canvas and scrollbar
        button_canvas.pack(side="left", fill="y", expand=True)
        button_scrollbar.pack(side="right", fill="y")
        
        # Create buttons based on variant
        self.flow_buttons = {}
        
        if self.button_variant == "individual":
            # Individual flow control buttons
            for i, flow in enumerate(flows, 1):
                btn = ttk.Button(button_frame, 
                               text=f"Flow {i} (stopped)",
                               command=lambda x=i: self.toggle_flow(x),
                               width=25)
                btn.pack(pady=2, padx=5)
                self.flow_buttons[i] = btn
        elif self.button_variant == "grouped":
            # Separate start and stop buttons for all flows
            start_command = variation_function if variation_function else self.start_all_flows
            
            start_btn = ttk.Button(button_frame,
                                 text="Start Variation",
                                 command=start_command,
                                 width=25)
            start_btn.pack(pady=2, padx=5)
            self.flow_buttons['start'] = start_btn
            
            stop_btn = ttk.Button(button_frame,
                                text="Stop All Flows",
                                command=self.stop_all_flows,
                                width=25)
            stop_btn.pack(pady=2, padx=5)
            self.flow_buttons['stop'] = stop_btn
        
        # Create frame for metrics
        metrics_frame = ttk.Frame(self.root)
        metrics_frame.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        metrics_frame.columnconfigure(0, weight=1)
        metrics_frame.rowconfigure(0, weight=1)
        
        # Create Treeview for metrics
        self.tree = ttk.Treeview(metrics_frame, show='headings')
        self.tree.grid(row=0, column=0, sticky='nsew')
        
        # Add scrollbars to treeview
        vsb = ttk.Scrollbar(metrics_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(metrics_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        # Configure treeview columns
        columns = ['metric'] + [f'flow_{i}' for i in range(len(flows))]
        self.tree['columns'] = columns
        
        # Configure column headings
        self.tree.heading('metric', text='Metric')
        for i, flow in enumerate(flows):
            self.tree.heading(f'flow_{i}', 
                            text=f"Flow {i+1}\n{flow['dst_ip']}\n{flow['rate']} Mbps")
            self.tree.column(f'flow_{i}', width=150, anchor='center')
        self.tree.column('metric', width=150, anchor='w')
        
        # Define metrics to display
        self.metrics_list = [
            ('State', 'transmit'),
            ('Bytes Tx', 'bytes_tx'),
            ('Bytes Rx', 'bytes_rx'),
            ('Frames Tx', 'frames_tx'),
            ('Frames Rx', 'frames_rx'),
            ('Tx Rate (fps)', 'frames_tx_rate'),
            ('Rx Rate (fps)', 'frames_rx_rate'),
            ('Latency Max (ns)', 'latency.maximum_ns'),
            ('Latency Min (ns)', 'latency.minimum_ns'),
            ('Latency Avg (ns)', 'latency.average_ns')
        ]
        
        # Initialize treeview rows
        for label, _ in self.metrics_list:
            self.tree.insert('', 'end', values=[label] + ['N/A'] * len(dst_ips))
        
        # Bind keyboard shortcuts
        self.root.bind('<Key>', self.handle_key)
        
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start metrics update thread
        self.running = True
        self.metrics_thread = threading.Thread(target=self.update_metrics)
        self.metrics_thread.daemon = True
        self.metrics_thread.start()
    
    def update_metrics(self):
        while self.running:
            mr = api.metrics_request()
            mr.flow.flow_names = []
            metrics = api.get_metrics(mr).flow_metrics # type: ignore
            
            # Update each row in the treeview
            for item in self.tree.get_children():
                row_values = list(self.tree.item(item)['values'])
                metric_name = next(m[1] for m in self.metrics_list if m[0] == row_values[0])
                
                for i, flow in enumerate(metrics):
                    value = flow
                    for part in metric_name.split('.'):
                        value = getattr(value, part)
                    if isinstance(value, (int, float)):
                        value = f"{value:,}"
                    row_values[i + 1] = value
                
                self.tree.item(item, values=row_values)
            
            time.sleep(1)
    
    def on_closing(self):
        if any(self.flow_states.values()):
            stop_window = tk.Toplevel(self.root)
            stop_window.title("Warning - Stopping Flows")
            stop_window.geometry("400x200")
            stop_window.transient(self.root)  # Make it float on top of main window
            stop_window.grab_set()  # Make it modal
            
            # Prevent closing the warning window
            stop_window.protocol("WM_DELETE_WINDOW", lambda: None)
            
            # Create a progress frame
            progress_frame = ttk.Frame(stop_window, padding="20")
            progress_frame.pack(fill=tk.BOTH, expand=True)
            
            label = ttk.Label(progress_frame, 
                text="Stopping all active flows...\nPlease wait while flows are being stopped.",
                justify=tk.CENTER)
            label.pack(pady=10)
            
            # Add progress bar
            progress = ttk.Progressbar(progress_frame, mode='indeterminate')
            progress.pack(fill=tk.X, pady=10)
            progress.start()
            
            # Add status label
            status_label = ttk.Label(progress_frame, text="")
            status_label.pack(pady=10)
            
            # Stop all active flows
            active_flows = sum(1 for state in self.flow_states.values() if state)
            stopped_flows = 0
            
            for key, state in self.flow_states.items():
                if state:
                    self.toggle_flow(key)
                    stopped_flows += 1
                    status_label.config(
                        text=f"Stopped {stopped_flows} of {active_flows} flows...")
                    self.root.update()
            
            def check_flows():
                if any(self.flow_states.values()):
                    stop_window.after(500, check_flows)
                else:
                    progress.stop()
                    status_label.config(text="All flows stopped. Closing application...")
                    self.root.update()
                    self.root.after(1000, lambda: self.finish_closing(stop_window))
            
            check_flows()
        else:
            self.finish_closing()
    
    def finish_closing(self, stop_window=None):
        self.running = False
        if stop_window:
            stop_window.destroy()
        self.root.destroy()

    def handle_key(self, event):
        if self.button_variant != "individual":
            return
        try:
            key = int(event.char)
            # Only handle keys 1-9 and only if flow exists
            if 1 <= key <= min(9, len(self.flows)):
                self.toggle_flow(key)
        except ValueError:
            pass
    
    def toggle_flow(self, key):
        flow_name = self.flows[key-1]['name']
        dst_ip = self.flows[key-1]['dst_ip']
        
        self.flow_states[key] = not self.flow_states[key]
        
        # Send POST request BEFORE starting a flow
        if self.flow_states[key]:  # About to start
            encoded_ip = urllib.parse.quote(dst_ip, safe='')
            try:
                response = requests.post(f"{NCS_API_LOCATION}/flows/{encoded_ip}")
                logger.info(f"POST request sent to NCS API for flow {key} (dst: {dst_ip}): {response.status_code}")
            except Exception as e:
                logger.error(f"Failed to send POST request for flow {key}: {e}")
        
        self.cs.traffic.flow_transmit.flow_names = [flow_name]
        self.cs.traffic.flow_transmit.state = (self.cs.traffic.flow_transmit.START 
            if self.flow_states[key] else self.cs.traffic.flow_transmit.STOP)
        self.api.set_control_state(self.cs)
        
        # Send DELETE request AFTER stopping a flow
        if not self.flow_states[key]:  # Just stopped
            encoded_ip = urllib.parse.quote(dst_ip, safe='')
            try:
                response = requests.delete(f"{NCS_API_LOCATION}/flows/{encoded_ip}")
                logger.info(f"DELETE request sent to NCS API for flow {key} (dst: {dst_ip}): {response.status_code}")
            except Exception as e:
                logger.error(f"Failed to send DELETE request for flow {key}: {e}")
        
        status = "started" if self.flow_states[key] else "stopped"
        btn_text = f"Flow {key} ({status})"
        self.flow_buttons[key].configure(text=btn_text)

    def start_all_flows(self):
        """Start all flows (default behavior when no variation function is provided)"""
        self.cs.traffic.flow_transmit.flow_names = []
        self.cs.traffic.flow_transmit.state = self.cs.traffic.flow_transmit.START
        self.api.set_control_state(self.cs)
        
        # Update all flow states
        for key in self.flow_states:
            self.flow_states[key] = True
        
        logger.info("Started all flows")

    def stop_all_flows(self):
        """Stop all flows and variation thread if running"""
        global variation_thread, variation_stop_event, variation_running
        
        # Stop the variation thread if it's running
        if variation_stop_event is not None:
            logger.info("Stopping variation thread...")
            variation_stop_event.set()
            variation_running = False
            
            # Re-enable start button
            if 'start' in self.flow_buttons:
                self.flow_buttons['start'].configure(state='normal', text="Start Variation")
        
        # Stop all traffic flows
        self.cs.traffic.flow_transmit.flow_names = []
        self.cs.traffic.flow_transmit.state = self.cs.traffic.flow_transmit.STOP
        self.api.set_control_state(self.cs)
        
        # Send DELETE requests for each flow
        for flow in self.flows:
            dst_ip = flow['dst_ip']
            encoded_ip = urllib.parse.quote(dst_ip, safe='')
            try:
                response = requests.delete(f"{NCS_API_LOCATION}/flows/{encoded_ip}")
                logger.info(f"DELETE request sent to NCS API for flow (dst: {dst_ip}): {response.status_code}")
            except Exception as e:
                logger.error(f"Failed to send DELETE request for flow (dst: {dst_ip}): {e}")
        
        # Update all flow states
        for key in self.flow_states:
            self.flow_states[key] = False
        
        logger.info("Stopped all flows")

    def run(self):
        self.root.mainloop()

# Create GUI with specified button variant and variation function

gui = TrafficControlGUI(api, cs, configured_flows, button_variant=BUTTON_VARIANT, variation_function=gui_variation_function)
gui.run()
