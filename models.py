import pandas as pd
import streamlit as st


def _df(name, rows, columns=None):
    if name not in st.session_state:
        st.session_state[name] = pd.DataFrame(rows, columns=columns)
    return st.session_state[name]


def initialize_data():
    if st.session_state.get("initialized"):
        return

    st.session_state.sites = pd.DataFrame([
        {"site_id": 1, "name": "Houlton-Maine-DC1", "address": "Houlton, ME"},
    ])

    st.session_state.racks = pd.DataFrame([
        {"rack_id": 1, "site_id": 1, "room": "CO", "name": "CO-R01", "u_height": 42},
        {"rack_id": 2, "site_id": 1, "room": "OSP", "name": "OSP/TAP Inventory", "u_height": 42},
    ])

    st.session_state.devices = pd.DataFrame([
        {"device_id": 1, "rack_id": 1, "name": "CO-Fiber-Panel-01", "role": "fiber_patch_panel", "position": 1, "u_height": 4, "port_count": 144, "port_prefix": "COF"},
        {"device_id": 2, "rack_id": 1, "name": "Core-Switch-01", "role": "network_device", "position": 8, "u_height": 1, "port_count": 48, "port_prefix": "Gi1/0"},
    ])

    st.session_state.ports = build_ports_from_devices(st.session_state.devices)

    st.session_state.cables = pd.DataFrame([
        {
            "cable_id": "CBL-001",
            "cable_type": "fiber",
            "color": "blue",
            "fiber_count": 144,
            "subtype": "co_panel",
            "a_port_id": 1,
            "z_port_id": None,
            "a_description": "CO-Fiber-Panel-01 COF-001",
            "z_description": "OSP",
            "length": None,
            "strand": "49",
            "site_id": 1,
            "site_name": "Houlton-Maine-DC1",
            "project": "",
            "location": "",
        },
    ])

    st.session_state.circuits = pd.DataFrame(columns=[
        "circuit_id", "carrier", "circuit_type", "bandwidth", "status", "a_end", "z_end", "cable_ids", "notes",
        "customer", "tap", "tap_port", "co_fiber", "street", "pole", "project", "location"
    ])

    st.session_state.tap_records = pd.DataFrame(columns=[
        "tap", "tap_port", "cable", "customer", "co_fiber", "pole", "street", "circuit_id", "status", "project", "location"
    ])

    st.session_state.change_log = pd.DataFrame(columns=[
        "timestamp", "event_type", "entity", "entity_id", "details",
    ])

    st.session_state.initialized = True


def build_ports_from_devices(devices):
    rows = []
    port_id = 1
    for _, dev in devices.iterrows():
        count = int(dev.get("port_count", 0) or 0)
        prefix = str(dev.get("port_prefix") or "P")
        role = str(dev.get("role") or "")
        ptype = "RJ45" if "ethernet" in role or "switch" in role or "network" in role else "LC"
        for idx in range(1, count + 1):
            rows.append({
                "port_id": port_id,
                "device_id": int(dev["device_id"]),
                "name": f"{prefix}-{idx:03d}" if prefix.upper() == "COF" else f"{prefix}/{idx}" if "Gi" in prefix else f"{prefix}-{idx:02d}",
                "type": ptype,
                "side": "front",
            })
            port_id += 1
    return pd.DataFrame(rows)


def ensure_ports_for_device(device_id):
    devices = st.session_state.devices
    dev = devices[devices["device_id"] == device_id]
    if dev.empty:
        return
    existing = st.session_state.ports[st.session_state.ports["device_id"] == device_id]
    port_count = int(dev.iloc[0].get("port_count", 0) or 0)
    if len(existing) == port_count:
        return
    st.session_state.ports = st.session_state.ports[st.session_state.ports["device_id"] != device_id].copy()
    next_id = int(st.session_state.ports["port_id"].max() + 1) if not st.session_state.ports.empty else 1
    prefix = str(dev.iloc[0].get("port_prefix") or "P")
    role = str(dev.iloc[0].get("role") or "")
    ptype = "RJ45" if "ethernet" in role or "switch" in role or "network" in role else "LC"
    rows = []
    for idx in range(1, port_count + 1):
        rows.append({
            "port_id": next_id,
            "device_id": int(device_id),
            "name": f"{prefix}-{idx:03d}" if prefix.upper() == "COF" else f"{prefix}/{idx}" if "Gi" in prefix else f"{prefix}-{idx:02d}",
            "type": ptype,
            "side": "front",
        })
        next_id += 1
    st.session_state.ports = pd.concat([st.session_state.ports, pd.DataFrame(rows)], ignore_index=True)


def used_port_ids():
    if st.session_state.cables.empty:
        return set()
    ids = []
    for col in ["a_port_id", "z_port_id"]:
        if col in st.session_state.cables.columns:
            ids.extend(st.session_state.cables[col].dropna().astype(int).tolist())
    return set(ids)


def port_label(port_id):
    if port_id is None or pd.isna(port_id):
        return "External / Unknown"
    ports = st.session_state.ports
    devices = st.session_state.devices
    p = ports[ports["port_id"] == int(port_id)]
    if p.empty:
        return f"Port {port_id}"
    p = p.iloc[0]
    d = devices[devices["device_id"] == int(p["device_id"])]
    dname = d.iloc[0]["name"] if not d.empty else "Unknown Device"
    return f"{dname} / {p['name']}"


def circuits_for_port(port_id):
    cable_ids = st.session_state.cables[
        (st.session_state.cables["a_port_id"] == port_id) | (st.session_state.cables["z_port_id"] == port_id)
    ]["cable_id"].astype(str).tolist() if not st.session_state.cables.empty else []
    if not cable_ids or st.session_state.circuits.empty:
        return pd.DataFrame(columns=st.session_state.circuits.columns)
    def touches(value):
        if isinstance(value, list):
            return any(str(x) in cable_ids for x in value)
        return any(cid in str(value) for cid in cable_ids)
    return st.session_state.circuits[st.session_state.circuits["cable_ids"].apply(touches)].copy()
