from snappi import Config, Flow, Device
import time
import threading
import requests
import urllib.parse

BUTTON_VARIANT = "grouped"

def define_flow(
    cfg: Config, 
    name: str, 
    tx_device: Device, 
    rx_device: Device, 
    packet_size: int, 
    rate_mbps: float, 
    src_ip: str, 
    dst_ip: str, 
    src_mac: str, 
    dst_mac: str
) -> Flow:
    """
    Configure a network flow with fixed packet size and transmission rate.
    
    Creates and configures a bidirectional network flow between two devices with specified
    packet characteristics, rate limiting, and protocol headers.
    
    Args:
        cfg: Configuration object containing flow definitions
        name (str): Name identifier for the flow
        tx_device: Transmitting device object
        rx_device: Receiving device object  
        packet_size (int): Fixed size in bytes for all packets in the flow
        rate_mbps (float): Transmission rate in megabits per second
        src_ip (str): Source IPv6 address
        dst_ip (str): Destination IPv6 address
        src_mac (str): Source MAC address
        dst_mac (str): Destination MAC address
    
    Returns:
        None
        
    Note:
        - Enables flow metrics including timestamps and cut-through latency measurement
        - Uses UDP protocol with fixed source and destination ports (1234)
        - Configures Ethernet/IPv6/UDP packet headers
    """
    
    # Configure a flow and set previously created test port as one of endpoints
    flow = cfg.flows.add(name=name)

    flow.tx_rx.device.tx_names = [tx_device.name]
    flow.tx_rx.device.rx_names = [rx_device.name]

    # and enable tracking flow metrics
    flow.metrics.enable = True
    flow.metrics.timestamps = True
    flow.metrics.latency.enable = True
    flow.metrics.latency.mode = "cut_through"

    # and fixed byte size of all packets in the flow
    flow.size.fixed = packet_size

    flow.rate.mbps = rate_mbps

    # Configure protocol headers for all packets in the flow
    eth, ip, udp = flow.packet.ethernet().ipv6().udp()

    eth.src.value = src_mac
    eth.dst.value = dst_mac

    ip.src.value = src_ip
    ip.dst.value = dst_ip

    udp.src_port.value = 1234
    udp.dst_port.value = 1234

    return flow

def variation_function(api, cfg, NCS_API_LOCATION, variation_interval: int, simultaneous_flows: list):
    """
    Handle flow start/stop variations based on time intervals and flow counts.
    This function manages the transmission of network flows by starting and stopping them
    according to a predefined schedule. It uses the Snappi API to control the state of the
    traffic flows defined in the configuration object.
    Runs in a separate thread to avoid blocking the GUI.
    
    Args:
        api: Snappi API object for control state operations
        cfg: Configuration object containing flow definitions
        variation_interval (int): Time interval in seconds between flow changes
        simultaneous_flows (list): Array of flow counts per interval
    
    Returns:
        tuple: (variation_thread, stop_event) for controlling the thread
    """
    # Create a stop event to control the thread
    stop_event = threading.Event()
    
    def variation_worker():
        # Get control state
        cs = api.control_state()
        
        # Storage experiment start time 
        start_time = time.time()
        current_active_flows = 0
        
        # Main variation loop - runs continuously until stopped
        for interval_index, target_flows in enumerate(simultaneous_flows):
            # Wait for the next interval
            if interval_index > 0:
                while time.time() - start_time < variation_interval * interval_index:
                    if stop_event.wait(1):
                        return
            
            # Determine flows to start and stop
            flows_to_start = []
            flows_to_stop = []
            
            if target_flows > current_active_flows:
                # Need to start more flows
                flows_to_start = [cfg.flows[i].name for i in range(current_active_flows, min(target_flows, len(cfg.flows)))]
            elif target_flows < current_active_flows:
                # Need to stop some flows
                flows_to_stop = [cfg.flows[i].name for i in range(target_flows, current_active_flows)]
            
            # Process flow changes
            def send_api_request(flow_name, method):
                dst_ip = flow_name.split('_')[-1]  # Assuming flow name format is 'flow_<dst_ip>'
                encoded_ip = urllib.parse.quote(dst_ip, safe='')
                url = f"{NCS_API_LOCATION}/flows/{encoded_ip}"
                
                try:
                    response = requests.delete(url) if method == 'DELETE' else requests.post(url)
                    
                    # Handle response
                    try:
                        response_data = response.json()
                        message = response_data.get('error' if response.status_code >= 400 else 'message', 'Unknown')
                    except:
                        message = 'No response data'
                    
                    print(f"{method} request for flow {flow_name} (IP: {dst_ip}), status: {response.status_code}, response: {message}")
                    
                except Exception as e:
                    print(f"Error sending {method} request for flow {flow_name}: {e}")
            
            # Stop flows first
            if flows_to_stop:
                for flow_name in flows_to_stop:
                    send_api_request(flow_name, 'DELETE')
                
                cs.traffic.flow_transmit.flow_names = flows_to_stop
                cs.traffic.flow_transmit.state = cs.traffic.flow_transmit.STOP
                api.set_control_state(cs)
            
            # Start flows
            if flows_to_start:
                for flow_name in flows_to_start:
                    send_api_request(flow_name, 'POST')
                
                cs.traffic.flow_transmit.flow_names = flows_to_start
                cs.traffic.flow_transmit.state = cs.traffic.flow_transmit.START
                api.set_control_state(cs)
            
            # Update current active flows count
            current_active_flows = target_flows
            
            # Print current state
            elapsed_time = time.time() - start_time
            # Add bounds checking to prevent IndexError
            active_flow_names = [cfg.flows[i].name for i in range(min(current_active_flows, len(cfg.flows)))]
            print(f"Time {elapsed_time:.1f}s - Interval {interval_index + 1}: {current_active_flows} active flows: {active_flow_names}")
        
        # Stop all remaining flows at the end
        print("Experiment finished, stopping all remaining traffic...")
        if current_active_flows > 0:
            # Add bounds checking here too
            remaining_flows = [cfg.flows[i].name for i in range(min(current_active_flows, len(cfg.flows)))]
            
            for flow_name in remaining_flows:
                send_api_request(flow_name, 'DELETE')
            
            cs.traffic.flow_transmit.flow_names = []
            cs.traffic.flow_transmit.state = cs.traffic.flow_transmit.STOP
            api.set_control_state(cs)
        
        print("Variation thread completed")
    
    # Start the variation worker in a separate daemon thread
    variation_thread = threading.Thread(target=variation_worker, daemon=True)
    variation_thread.start()
    
    return variation_thread, stop_event
