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
        
        # Get the first value from simultaneous_flows array
        initial_flows_count = simultaneous_flows[0]
        
        # Select only the first N flows from the configuration
        flow_names = [flow.name for flow in cfg.flows[:initial_flows_count]]
        
        # Set these flows to be transmitted
        cs.traffic.flow_transmit.flow_names = flow_names
        
        print(f"Starting {initial_flows_count} flows: {flow_names}")
        
        # Set flows to start transmitting
        cs.traffic.flow_transmit.state = cs.traffic.flow_transmit.START
        
        # Storage experiment start time 
        start_time = time.time()
        flow_list_index = 0
        
        # Send updated control state to OTG
        api.set_control_state(cs)
        
        # Main variation loop - runs continuously until stopped
        while not stop_event.is_set():
            current_time = time.time()
            
            # Check if a variation interval has passed
            if current_time - start_time >= variation_interval * (flow_list_index + 1):
                
                # Check if we have more flow configurations to apply
                if flow_list_index + 1 >= len(simultaneous_flows):
                    print("No more flow configurations to apply, stopping traffic.")
                    
                    cs.traffic.flow_transmit.flow_names = []
                    cs.traffic.flow_transmit.state = cs.traffic.flow_transmit.STOP
                    api.set_control_state(cs)
                    print("Experiment finished, stopping all traffic...")
                    break
                
                # Get currently running flows
                current_flows = simultaneous_flows[flow_list_index]
                
                # Move to next flow configuration
                flow_list_index = flow_list_index + 1
                new_flow_count = simultaneous_flows[flow_list_index]
                
                # Get which flows to start/stop based on new count
                flow_difference = new_flow_count - current_flows
                
                # Set flows to start or stop based on the difference
                starting_flows = []
                stopping_flows = []
                
                if flow_difference > 0:
                    for i in range(current_flows + 1, new_flow_count + 1):
                        starting_flows.append(cfg.flows[i-1].name)
                
                elif flow_difference < 0:
                    for i in range(new_flow_count + 1, current_flows + 1):
                        stopping_flows.append(cfg.flows[i-1].name)
                
                else:
                    print(f"Time {current_time - start_time:.1f}s: No change in flow count ({new_flow_count})")
                    continue
                
                # Stop flows that are no longer needed
                if len(stopping_flows) > 0:
                    cs.traffic.flow_transmit.flow_names = stopping_flows
                    cs.traffic.flow_transmit.state = cs.traffic.flow_transmit.STOP
                    api.set_control_state(cs)
                    
                    # Send DELETE request to NCS API for each stopped flow
                    for flow_name in stopping_flows:
                        # Find the flow configuration to get destination IP
                        for flow in cfg.flows:
                            if flow.name == flow_name:
                                dst_ip = flow.packet.ethernet().ipv6().dst.value
                                encoded_ip = urllib.parse.quote(dst_ip, safe='')
                                delete_url = f"{NCS_API_LOCATION}/flows/{encoded_ip}"
                                
                                try:
                                    response = requests.delete(delete_url)
                                    print(f"DELETE request sent for flow {flow_name} (IP: {dst_ip}), status: {response.status_code}")
                                except Exception as e:
                                    print(f"Error sending DELETE request for flow {flow_name}: {e}")
                                break
                
                # Start new flows
                if len(starting_flows) > 0:
                    # Send POST request to NCS API for each starting flow                    
                    for flow_name in starting_flows:
                        # Find the flow configuration to get destination IP
                        for flow in cfg.flows:
                            if flow.name == flow_name:
                                dst_ip = flow.packet.ethernet().ipv6().dst.value
                                encoded_ip = urllib.parse.quote(dst_ip, safe='')
                                post_url = f"{NCS_API_LOCATION}/flows/{encoded_ip}"
                                
                                try:
                                    response = requests.post(post_url)
                                    print(f"POST request sent for flow {flow_name} (IP: {dst_ip}), status: {response.status_code}")
                                except Exception as e:
                                    print(f"Error sending POST request for flow {flow_name}: {e}")
                                break
                    
                    cs.traffic.flow_transmit.flow_names = starting_flows
                    cs.traffic.flow_transmit.state = cs.traffic.flow_transmit.START
                    api.set_control_state(cs)
                
                print(f"Time {current_time - start_time:.1f}s: Updated to {new_flow_count} flows: 1 to {new_flow_count}")
            
            # Sleep for 1 second before checking again, but check stop event periodically
            if stop_event.wait(1):
                break
        
        print("Variation thread stopped")
    
    # Start the variation worker in a separate daemon thread
    variation_thread = threading.Thread(target=variation_worker, daemon=True)
    variation_thread.start()
    
    return variation_thread, stop_event

