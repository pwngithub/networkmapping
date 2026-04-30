import ast
from collections import deque
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Colo Connection Tracker", layout="wide", page_icon="🖧")

# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
    .main-title {font-size: 2.0rem; font-weight: 800; margin-bottom: .25rem;}
    .subtle {color: #64748b; font-size: .95rem;}
    .card {border: 1px solid #e2e8f0; border-radius: 14px; padding: 14px; background: #ffffff; margin-bottom: 10px;}
    .device-card {border: 1px solid #cbd5e1; border-radius: 12px; padding: 10px; background: #f8fafc; margin-bottom: 8px;}
    .device-card-selected {border: 2px solid #2563eb; border-radius: 12px; padding: 10px; background: #eff6ff; margin-bottom: 8px;}
    .path-hop {border-left: 5px solid #2563eb; padding: 10px 14px; background:#f8fafc; border-radius: 10px; margin-bottom:8px;}
    .free-port {color:#15803d; font-weight:700;}
    .used-port {color:#b45309; font-weight:700;}
    .danger {color:#b91c1c; font-weight:700;}
    .pm-panel {border:1px solid #cbd5e1; border-radius:14px; padding:14px; background:#ffffff; margin-bottom:12px;}
    .pm-header {font-size:1.1rem; font-weight:800; color:#0f172a; margin-bottom:6px;}
    .pm-port-free {display:inline-block; min-width:82px; padding:8px; margin:4px; border-radius:10px; background:#dcfce7; border:1px solid #86efac; color:#166534; font-weight:700; text-align:center;}
    .pm-port-used {display:inline-block; min-width:82px; padding:8px; margin:4px; border-radius:10px; background:#fef3c7; border:1px solid #f59e0b; color:#92400e; font-weight:700; text-align:center;}
    .pm-path {display:flex; align-items:center; gap:8px; flex-wrap:wrap; padding:10px; border-radius:12px; background:#f8fafc; border:1px solid #e2e8f0;}
    .pm-node {border:1px solid #94a3b8; background:white; border-radius:12px; padding:10px; min-width:180px;}
    .pm-arrow {font-size:1.5rem; font-weight:900; color:#2563eb;}
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Helpers
# -----------------------------
def next_int_id(df: pd.DataFrame, col: str) -> int:
    if df.empty or col not in df.columns:
        return 1
    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    return int(vals.max() + 1) if not vals.empty else 1


def safe_list(value):
    if isinstance(value, list):
        return value
    if pd.isna(value) or value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return [x.strip() for x in value.split(",") if x.strip()]
    return []


def get_row(df_name: str, col: str, value):
    df = st.session_state[df_name]
    match = df[df[col].astype(str) == str(value)]
    return None if match.empty else match.iloc[0]


def port_label(port_id) -> str:
    port = get_row("ports", "port_id", port_id)
    if port is None:
        return str(port_id)
    device = get_row("devices", "device_id", port["device_id"])
    rack_name = ""
    if device is not None:
        rack = get_row("racks", "rack_id", device["rack_id"])
        rack_name = rack["name"] if rack is not None else ""
        return f"{rack_name} / {device['name']} / {port['name']}"
    return f"Port {port_id}"


def device_label(device_id) -> str:
    dev = get_row("devices", "device_id", device_id)
    if dev is None:
        return str(device_id)
    rack = get_row("racks", "rack_id", dev["rack_id"])
    rack_name = rack["name"] if rack is not None else "No Rack"
    return f"{rack_name} / {dev['name']}"


def endpoint_details(port_id, fallback_description="") -> dict:
    """Return readable details for one side of a cable/circuit."""
    if port_id in (None, "") or pd.isna(port_id):
        return {"site":"External / Unknown","room":"","rack":"","equipment":fallback_description or "External / handoff","role":"external","port":"No port assigned","full":fallback_description or "External / handoff"}
    port = get_row("ports", "port_id", port_id)
    if port is None:
        return {"site":"Unknown","room":"","rack":"","equipment":"Unknown equipment","role":"unknown","port":f"Port {port_id}","full":f"Unknown equipment / Port {port_id}"}
    dev = get_row("devices", "device_id", port["device_id"])
    rack = get_row("racks", "rack_id", dev["rack_id"]) if dev is not None else None
    site = get_row("sites", "site_id", rack["site_id"]) if rack is not None else None
    site_name = site["name"] if site is not None else "Unknown Site"
    room = rack["room"] if rack is not None and "room" in rack else ""
    rack_name = rack["name"] if rack is not None else "No Rack"
    equipment = dev["name"] if dev is not None else "Unknown Equipment"
    role = dev.get("role", "") if dev is not None else ""
    port_name = port["name"]
    return {"site":site_name,"room":room,"rack":rack_name,"equipment":equipment,"role":role,"port":port_name,"full":f"{site_name} / {room} / {rack_name} / {equipment} / {port_name}"}


def endpoint_card(title, details):
    role = f" ({details['role']})" if details.get("role") else ""
    return f"""
    <div style="border:1px solid #cbd5e1; border-radius:12px; padding:10px; background:#ffffff; height:100%;">
      <div style="font-size:.8rem; color:#64748b; font-weight:700;">{title}</div>
      <div style="font-size:1.02rem; font-weight:800; color:#0f172a;">{details['equipment']}{role}</div>
      <div style="font-size:.95rem; margin-top:4px;"><b>Port:</b> {details['port']}</div>
      <div style="font-size:.9rem; color:#475569;"><b>Rack:</b> {details['rack']} &nbsp; <b>Room:</b> {details['room']}</div>
      <div style="font-size:.9rem; color:#475569;"><b>Site:</b> {details['site']}</div>
    </div>
    """


def port_status(port_id):
    cables = st.session_state.cables
    used = cables[(cables["a_port_id"].astype(str) == str(port_id)) | (cables["z_port_id"].astype(str) == str(port_id))]
    circuits = []
    for _, c in st.session_state.circuits.iterrows():
        for cid in safe_list(c.get("cable_ids", [])):
            if cid in used["cable_id"].astype(str).tolist():
                circuits.append(c["circuit_id"])
    return used, sorted(set(circuits))


def ports_for_device(device_id):
    return st.session_state.ports[st.session_state.ports["device_id"].astype(str) == str(device_id)].copy()


def build_graph():
    graph = {}
    for _, cable in st.session_state.cables.iterrows():
        a = cable.get("a_port_id")
        z = cable.get("z_port_id")
        if pd.isna(a) or pd.isna(z) or a in (None, "") or z in (None, ""):
            continue
        a, z = int(a), int(z)
        graph.setdefault(a, []).append((z, cable["cable_id"]))
        graph.setdefault(z, []).append((a, cable["cable_id"]))
    return graph


def find_path(start_port, end_port):
    if not start_port or not end_port:
        return []
    start_port, end_port = int(start_port), int(end_port)
    graph = build_graph()
    q = deque([(start_port, [])])
    visited = {start_port}
    while q:
        node, path = q.popleft()
        if node == end_port:
            return path
        for nxt, cable_id in graph.get(node, []):
            if nxt not in visited:
                visited.add(nxt)
                q.append((nxt, path + [(node, nxt, cable_id)]))
    return []


def cable_type_color(cable_type):
    if "fiber" in cable_type:
        return "#2563eb"
    if "ethernet" in cable_type or "copper" in cable_type:
        return "#f97316"
    if "incoming" in cable_type:
        return "#7c3aed"
    return "#334155"


def show_port_table(device_id, key_prefix="port_table"):
    ports = ports_for_device(device_id)
    rows = []
    for _, p in ports.iterrows():
        used_cables, circuits = port_status(p["port_id"])
        rows.append({
            "port_id": p["port_id"],
            "Port": p["name"],
            "Type": p["type"],
            "Side": p.get("side", "front"),
            "Status": "USED" if not used_cables.empty else "AVAILABLE",
            "Cable(s)": ", ".join(used_cables["cable_id"].astype(str).tolist()),
            "Circuit(s)": ", ".join(circuits),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No ports have been created for this equipment yet.")
        return None
    st.dataframe(df.drop(columns=["port_id"]), use_container_width=True, hide_index=True)
    selected = st.selectbox(
        "Select a port",
        options=df["port_id"].tolist(),
        format_func=lambda x: f"{df[df['port_id']==x]['Port'].iloc[0]} — {df[df['port_id']==x]['Status'].iloc[0]}",
        key=f"{key_prefix}_select",
    )
    used_cables, circuits = port_status(selected)
    if circuits:
        st.warning(f"This port is already used by circuit(s): {', '.join(circuits)}")
        with st.expander("Show cable/circuit details", expanded=True):
            st.dataframe(used_cables, use_container_width=True, hide_index=True)
            st.dataframe(st.session_state.circuits[st.session_state.circuits["circuit_id"].isin(circuits)], use_container_width=True, hide_index=True)
    else:
        st.success("This port is available.")
    return selected



def make_auto_circuit_id(a_port_id, z_port_id, cable_id):
    base = f"AUTO-{cable_id}"
    existing = set(st.session_state.circuits.get("circuit_id", pd.Series(dtype=str)).astype(str).tolist())
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def circuits_using_port(port_id):
    used_cables, _ = port_status(port_id)
    cable_ids = set(used_cables["cable_id"].astype(str).tolist()) if not used_cables.empty else set()
    matches = []
    for _, c in st.session_state.circuits.iterrows():
        direct_match = str(c.get("a_port_id", "")) == str(port_id) or str(c.get("z_port_id", "")) == str(port_id)
        cable_match = bool(cable_ids.intersection(set(map(str, safe_list(c.get("cable_ids", []))))))
        if direct_match or cable_match:
            matches.append(str(c["circuit_id"]))
    return sorted(set(matches))


def circuits_using_cable(cable_id):
    matches = []
    for _, c in st.session_state.circuits.iterrows():
        if str(cable_id) in set(map(str, safe_list(c.get("cable_ids", [])))):
            matches.append(str(c["circuit_id"]))
    return sorted(set(matches))


def add_cable_to_circuit(circuit_id, cable_id, a_port_id=None, z_port_id=None):
    idxs = st.session_state.circuits.index[st.session_state.circuits["circuit_id"].astype(str) == str(circuit_id)].tolist()
    if not idxs:
        return False
    idx = idxs[0]
    ids = [str(x) for x in safe_list(st.session_state.circuits.at[idx, "cable_ids"])]
    if str(cable_id) not in ids:
        ids.append(str(cable_id))
    st.session_state.circuits.at[idx, "cable_ids"] = ids
    st.session_state.circuits.at[idx, "z_port_id"] = int(z_port_id) if z_port_id not in (None, "") else st.session_state.circuits.at[idx, "z_port_id"]
    return True


def create_auto_circuit_for_connection(a_port_id, z_port_id, cable_id, site_id, project_location, cable_type, notes=""):
    circuit_id = make_auto_circuit_id(a_port_id, z_port_id, cable_id)
    row = pd.DataFrame([{
        "circuit_id": circuit_id,
        "site_id": site_id,
        "project_location": project_location,
        "carrier_customer": "Auto-created",
        "service_type": "Cross-Connect" if cable_type in ("cross_connect", "fiber_patch", "ethernet_patch") else "Physical Connection",
        "bandwidth": "",
        "status": "documented",
        "a_port_id": int(a_port_id),
        "z_port_id": int(z_port_id),
        "cable_ids": [str(cable_id)],
        "notes": notes or "Auto-created from Connection Builder",
    }])
    st.session_state.circuits = pd.concat([st.session_state.circuits, row], ignore_index=True)
    return circuit_id


def merge_circuits(target_circuit_id, source_circuit_ids, delete_sources=True):
    target_idxs = st.session_state.circuits.index[st.session_state.circuits["circuit_id"].astype(str) == str(target_circuit_id)].tolist()
    if not target_idxs:
        return []
    target_idx = target_idxs[0]
    merged_cables = [str(x) for x in safe_list(st.session_state.circuits.at[target_idx, "cable_ids"])]
    merged_notes = str(st.session_state.circuits.at[target_idx, "notes"] or "")
    merged_from = []
    for source_id in source_circuit_ids:
        if str(source_id) == str(target_circuit_id):
            continue
        rows = st.session_state.circuits[st.session_state.circuits["circuit_id"].astype(str) == str(source_id)]
        if rows.empty:
            continue
        src = rows.iloc[0]
        for cid in safe_list(src.get("cable_ids", [])):
            if str(cid) not in merged_cables:
                merged_cables.append(str(cid))
        merged_notes += f"\nMerged from {source_id}: {src.get('notes', '')}"
        merged_from.append(str(source_id))
    st.session_state.circuits.at[target_idx, "cable_ids"] = merged_cables
    st.session_state.circuits.at[target_idx, "notes"] = merged_notes.strip()
    if delete_sources and merged_from:
        st.session_state.circuits = st.session_state.circuits[~st.session_state.circuits["circuit_id"].astype(str).isin(merged_from)]
    return merged_from

def port_connection_rows(port_id):
    used_cables, circuits = port_status(port_id)
    rows = []
    for _, cable in used_cables.iterrows():
        a = endpoint_details(cable.get("a_port_id"), cable.get("a_description", ""))
        z = endpoint_details(cable.get("z_port_id"), cable.get("z_description", ""))
        other = z if str(cable.get("a_port_id")) == str(port_id) else a
        rows.append({
            "Cable": cable["cable_id"],
            "Type": cable.get("cable_type", ""),
            "This Port": endpoint_details(port_id)["full"],
            "Connected To": other["full"],
            "Circuit(s)": ", ".join(circuits_using_cable(cable["cable_id"])),
            "Notes": cable.get("notes", ""),
        })
    return pd.DataFrame(rows)


def show_port_chips(device_id, title="Port Availability"):
    ports = ports_for_device(device_id)
    st.markdown(f'<div class="pm-header">{title}</div>', unsafe_allow_html=True)
    if ports.empty:
        st.info("No ports found for this equipment.")
        return None
    html = []
    status_map = {}
    for _, p in ports.iterrows():
        used_cables, circuits = port_status(p["port_id"])
        used = not used_cables.empty
        cls = "pm-port-used" if used else "pm-port-free"
        label = "USED" if used else "FREE"
        html.append(f'<span class="{cls}">{p["name"]}<br><small>{label}</small></span>')
        status_map[p["port_id"]] = label
    st.markdown("".join(html), unsafe_allow_html=True)
    selected = st.selectbox(
        "Open port details",
        ports["port_id"].tolist(),
        format_func=lambda pid: f"{ports[ports['port_id']==pid]['name'].iloc[0]} — {status_map.get(pid, '')}",
        key=f"pm_port_chip_{device_id}_{title}",
    )
    return selected


def show_circuit_path_diagram(circuit_id):
    if not circuit_id:
        return
    rows = st.session_state.circuits[st.session_state.circuits["circuit_id"].astype(str) == str(circuit_id)]
    if rows.empty:
        st.info("Circuit not found.")
        return
    circuit = rows.iloc[0]
    st.markdown(f"### Circuit Path: {circuit['circuit_id']}")
    st.caption(f"{circuit.get('carrier_customer','')} • {circuit.get('service_type','')} • {circuit.get('bandwidth','')} • {circuit.get('status','')}")
    cable_ids = safe_list(circuit.get("cable_ids", []))
    if not cable_ids:
        st.warning("No cable segments are linked to this circuit yet.")
        return
    for i, cable_id in enumerate(cable_ids, start=1):
        cable = get_row("cables", "cable_id", cable_id)
        if cable is None:
            continue
        a = endpoint_details(cable.get("a_port_id"), cable.get("a_description", ""))
        z = endpoint_details(cable.get("z_port_id"), cable.get("z_description", ""))
        st.markdown(f"""
            <div class="pm-path">
              <div class="pm-node"><b>A-End</b><br>{a['equipment']}<br><small>{a['rack']} / {a['port']}</small></div>
              <div class="pm-arrow">── {cable['cable_id']} ──▶</div>
              <div class="pm-node"><b>Z-End</b><br>{z['equipment']}<br><small>{z['rack']} / {z['port']}</small></div>
            </div>
            """, unsafe_allow_html=True)
        st.caption(f"Hop {i}: {cable.get('cable_type','')} • {cable.get('color','')} • {cable.get('strand','')}")


def equipment_utilization_df():
    rows = []
    for _, d in st.session_state.devices.iterrows():
        ports = ports_for_device(d["device_id"])
        used = 0
        for _, p in ports.iterrows():
            used_cables, _ = port_status(p["port_id"])
            if not used_cables.empty:
                used += 1
        total = len(ports)
        rows.append({
            "Equipment": device_label(d["device_id"]),
            "Type": d.get("role", ""),
            "Start U": d.get("position", ""),
            "Ports": total,
            "Used": used,
            "Available": total - used,
            "Utilization %": round((used / total * 100), 1) if total else 0,
        })
    return pd.DataFrame(rows)




def data_quality_report():
    """Basic consistency checks to highlight mapping issues."""
    findings = []

    def add(check, severity, count, details):
        findings.append({
            "Check": check,
            "Severity": severity,
            "Count": int(count),
            "Details": details,
        })

    cable_ids = st.session_state.cables["cable_id"].astype(str) if "cable_id" in st.session_state.cables.columns else pd.Series(dtype=str)
    circuit_ids = st.session_state.circuits["circuit_id"].astype(str) if "circuit_id" in st.session_state.circuits.columns else pd.Series(dtype=str)

    dup_cables = cable_ids[cable_ids.duplicated()]
    add("Duplicate cable IDs", "high" if not dup_cables.empty else "ok", len(dup_cables), ", ".join(sorted(set(dup_cables.tolist()))) if not dup_cables.empty else "None")

    dup_circuits = circuit_ids[circuit_ids.duplicated()]
    add("Duplicate circuit IDs", "high" if not dup_circuits.empty else "ok", len(dup_circuits), ", ".join(sorted(set(dup_circuits.tolist()))) if not dup_circuits.empty else "None")

    known_ports = set(st.session_state.ports.get("port_id", pd.Series(dtype=int)).dropna().astype(int).tolist())
    bad_endpoint_rows = []
    for _, cable in st.session_state.cables.iterrows():
        for side in ("a_port_id", "z_port_id"):
            pid = cable.get(side)
            if pid in (None, "") or pd.isna(pid):
                continue
            if int(pid) not in known_ports:
                bad_endpoint_rows.append(f"{cable.get('cable_id')}:{side}={int(pid)}")
    add("Cables referencing unknown ports", "high" if bad_endpoint_rows else "ok", len(bad_endpoint_rows), "; ".join(bad_endpoint_rows[:20]) if bad_endpoint_rows else "None")

    all_cable_ids = set(cable_ids.tolist())
    missing_cable_refs = []
    for _, circuit in st.session_state.circuits.iterrows():
        cid = circuit.get("circuit_id")
        for linked in safe_list(circuit.get("cable_ids", [])):
            if str(linked) not in all_cable_ids:
                missing_cable_refs.append(f"{cid}:{linked}")
    add("Circuits with missing cable references", "medium" if missing_cable_refs else "ok", len(missing_cable_refs), "; ".join(missing_cable_refs[:20]) if missing_cable_refs else "None")

    return pd.DataFrame(findings)

def add_ports_for_device(device_id, port_count, port_prefix, port_type, side="front"):
    rows = []
    start = next_int_id(st.session_state.ports, "port_id")
    for i in range(1, int(port_count) + 1):
        rows.append({
            "port_id": start + i - 1,
            "device_id": device_id,
            "name": f"{port_prefix}{i:02d}",
            "type": port_type,
            "side": side,
        })
    if rows:
        st.session_state.ports = pd.concat([st.session_state.ports, pd.DataFrame(rows)], ignore_index=True)


def gpon_role_defaults(role):
    role = str(role or "")
    if role == "gpon_splitter_1x32":
        return {"port_count": 33, "port_type": "LC", "prefix": "SP"}
    if role == "gpon_olt":
        return {"port_count": 16, "port_type": "SFP+", "prefix": "PON"}
    return None


def normalize_import_columns(df: pd.DataFrame):
    """Map common TAP spreadsheet header variants to canonical column names."""
    alias_map = {
        "Tap": ["tap", "tap id", "tap_name"],
        "PORT": ["port", "tap port", "port #", "port number", "tap_port"],
        "Cable": ["cable", "cable id", "cableid", "drop cable"],
        "Customer": ["customer", "customer name", "subscriber", "account"],
        "CO Fiber": ["co fiber", "co_fiber", "cofiber", "fiber", "co strand"],
        "Pole": ["pole", "pole #", "pole number", "pole_no"],
        "Street": ["street", "road", "address", "location street"],
    }
    normalized = {str(c).strip().lower(): c for c in df.columns}
    rename = {}
    for canonical, aliases in alias_map.items():
        for alias in aliases:
            if alias in normalized:
                rename[normalized[alias]] = canonical
                break
    return df.rename(columns=rename)


def init_data():
    if st.session_state.get("initialized"):
        return
    st.session_state.sites = pd.DataFrame([
        {"site_id": 1, "name": "Houlton-Maine-DC1", "address": "Houlton, ME", "notes": "Main colo"}
    ])
    st.session_state.racks = pd.DataFrame([
        {"rack_id": 1, "site_id": 1, "room": "Hall A", "name": "R01", "u_height": 42},
        {"rack_id": 2, "site_id": 1, "room": "Hall A", "name": "R02", "u_height": 42},
    ])
    st.session_state.devices = pd.DataFrame([
        {"device_id": 1, "rack_id": 1, "name": "MMR-Fiber-Panel-01", "role": "fiber_patch_panel", "position": 1, "u_height": 2, "port_count": 24},
        {"device_id": 2, "rack_id": 1, "name": "ODF-01", "role": "fiber_patch_panel", "position": 5, "u_height": 4, "port_count": 48},
        {"device_id": 3, "rack_id": 2, "name": "Core-Router-01", "role": "router", "position": 10, "u_height": 2, "port_count": 8},
    ])
    st.session_state.ports = pd.DataFrame(columns=["port_id", "device_id", "name", "type", "side"])
    add_ports_for_device(1, 24, "LC-", "LC")
    add_ports_for_device(2, 48, "LC-", "LC")
    add_ports_for_device(3, 8, "Te0/0/", "SFP+")
    st.session_state.cables = pd.DataFrame([
        {"cable_id": "CBL-IN-001", "site_id": 1, "project_location": "Example", "cable_type": "incoming_fiber", "color": "yellow", "strand": "F01", "a_port_id": 1, "z_port_id": 25, "a_description": "Carrier handoff", "z_description": "ODF", "length": 20, "notes": "Incoming carrier fiber"},
        {"cable_id": "PATCH-001", "site_id": 1, "project_location": "Example", "cable_type": "fiber_patch", "color": "blue", "strand": "", "a_port_id": 25, "z_port_id": 73, "a_description": "ODF", "z_description": "Router", "length": 3, "notes": "Patch to router"},
    ])
    st.session_state.circuits = pd.DataFrame([
        {"circuit_id": "FIRSTLIGHT-DIA-10G", "site_id": 1, "project_location": "Example", "carrier_customer": "FirstLight", "service_type": "DIA", "bandwidth": "10G", "status": "active", "a_port_id": 1, "z_port_id": 73, "cable_ids": ["CBL-IN-001", "PATCH-001"], "notes": "Example circuit path"}
    ])
    st.session_state.work_orders = pd.DataFrame(columns=["wo_id", "created", "type", "status", "site_id", "description", "circuit_id", "assigned_to", "notes"])
    st.session_state.initialized = True


init_data()

st.markdown('<div class="main-title">🖧 Colo Connection Tracker</div>', unsafe_allow_html=True)
st.markdown('<div class="subtle">Track incoming cables, patch panels, patch cables, equipment ports, and the circuits/services riding over them.</div>', unsafe_allow_html=True)

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Patchmanager View", "Sites & Racks", "Equipment & Ports", "Connection Builder", "Circuits", "Trace / Search", "Work Orders", "Reports", "Import TAP Sheet"],
)

# -----------------------------
# Dashboard
# -----------------------------
if page == "Dashboard":
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Sites", len(st.session_state.sites))
    c2.metric("Racks", len(st.session_state.racks))
    c3.metric("Equipment", len(st.session_state.devices))
    c4.metric("Physical Cables", len(st.session_state.cables))
    c5.metric("Circuits", len(st.session_state.circuits))

    st.subheader("How this app is organized")
    st.markdown(
        """
        **Physical connections come first.** A circuit is the service riding over one or more physical cable segments.

        Example path:
        `Carrier entrance fiber → MMR patch panel → ODF → fiber patch cable → router/switch port → circuit/service`
        """
    )
    st.subheader("Recent physical cables")
    st.dataframe(st.session_state.cables.tail(10), use_container_width=True, hide_index=True)

# -----------------------------
# Sites & Racks
# -----------------------------
elif page == "Sites & Racks":
    st.header("Sites & Racks")
    tab1, tab2 = st.tabs(["Sites", "Racks"])
    with tab1:
        st.data_editor(st.session_state.sites, use_container_width=True, num_rows="dynamic", key="sites_editor")
        if st.button("Save Site Changes"):
            st.session_state.sites = st.session_state.sites_editor
            st.success("Sites saved.")
            st.rerun()
    with tab2:
        st.data_editor(st.session_state.racks, use_container_width=True, num_rows="dynamic", key="racks_editor")
        if st.button("Save Rack Changes"):
            st.session_state.racks = st.session_state.racks_editor
            st.success("Racks saved.")
            st.rerun()

        st.subheader("Clean Rack Map")
        site_id = st.selectbox("Site", st.session_state.sites["site_id"], format_func=lambda x: get_row("sites", "site_id", x)["name"])
        racks = st.session_state.racks[st.session_state.racks["site_id"] == site_id]
        if not racks.empty:
            rack_id = st.selectbox("Rack", racks["rack_id"], format_func=lambda x: get_row("racks", "rack_id", x)["name"])
            rack = get_row("racks", "rack_id", rack_id)
            devs = st.session_state.devices[st.session_state.devices["rack_id"] == rack_id].sort_values("position")
            st.markdown(f"### {rack['name']} — {rack['room']} — {rack['u_height']}U")
            used_u = set()
            for _, d in devs.iterrows():
                start = int(d["position"])
                end = start + int(d["u_height"]) - 1
                used_u.update(range(start, end + 1))
                ports = ports_for_device(d["device_id"])
                used = 0
                for _, p in ports.iterrows():
                    c, _ = port_status(p["port_id"])
                    if not c.empty:
                        used += 1
                st.markdown(
                    f"""
                    <div class="device-card">
                    <b>U{start}–U{end}</b> &nbsp; <b>{d['name']}</b><br>
                    <span class="subtle">{d['role']} • {used}/{len(ports)} ports used • {len(ports)-used} available</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            empty_count = int(rack["u_height"]) - len(used_u)
            st.caption(f"{empty_count} open U positions in this rack.")

# -----------------------------
# Equipment & Ports
# -----------------------------
elif page == "Equipment & Ports":
    st.header("Equipment & Ports")
    tab1, tab2, tab3 = st.tabs(["View Equipment", "Add Equipment", "Edit/Delete"])

    with tab1:
        site_id = st.selectbox("Site", st.session_state.sites["site_id"], format_func=lambda x: get_row("sites", "site_id", x)["name"], key="eq_site_view")
        rack_options = st.session_state.racks[st.session_state.racks["site_id"] == site_id]
        if rack_options.empty:
            st.info("Create a rack first.")
        else:
            rack_id = st.selectbox("Rack", rack_options["rack_id"], format_func=lambda x: get_row("racks", "rack_id", x)["name"], key="eq_rack_view")
            devs = st.session_state.devices[st.session_state.devices["rack_id"] == rack_id]
            if devs.empty:
                st.info("No equipment in this rack yet.")
            else:
                device_id = st.selectbox("Equipment / Patch Panel", devs["device_id"], format_func=device_label, key="eq_device_view")
                st.subheader(device_label(device_id))
                selected_port = show_port_table(device_id, key_prefix="equipment_view")
                if selected_port:
                    col_a, col_z = st.columns(2)
                    if col_a.button("Use this as A-End", type="primary"):
                        st.session_state.builder_a_port = selected_port
                        st.success("A-End selected. Go to Connection Builder.")
                    if col_z.button("Use this as Z-End", type="primary"):
                        st.session_state.builder_z_port = selected_port
                        st.success("Z-End selected. Go to Connection Builder.")

    with tab2:
        st.subheader("Add Equipment or Patch Panel")
        with st.form("add_equipment"):
            site_id = st.selectbox("Site", st.session_state.sites["site_id"], format_func=lambda x: get_row("sites", "site_id", x)["name"], key="add_eq_site")
            rack_options = st.session_state.racks[st.session_state.racks["site_id"] == site_id]
            rack_id = st.selectbox("Rack", rack_options["rack_id"], format_func=lambda x: get_row("racks", "rack_id", x)["name"]) if not rack_options.empty else None
            name = st.text_input("Name", placeholder="ODF-02 / Customer-Patch-Panel-01 / Core-Switch-01")
            role = st.selectbox("Type", ["fiber_patch_panel", "gpon_splitter_1x32", "gpon_olt", "ethernet_patch_panel", "switch", "router", "firewall", "customer_equipment", "carrier_demarc", "other"])
            c1, c2, c3 = st.columns(3)
            position = c1.number_input("Start U", min_value=1, max_value=52, value=1)
            default_cfg = gpon_role_defaults(role)
            default_port_count = int(default_cfg["port_count"]) if default_cfg else 24
            default_port_type = default_cfg["port_type"] if default_cfg else "LC"
            default_prefix = default_cfg["prefix"] if default_cfg else ("LC-" if "fiber" in role else "Gi1/0/")
            u_height = c2.number_input("Height in U", min_value=1, max_value=20, value=2 if role == "gpon_splitter_1x32" else 1)
            port_count = c3.number_input("Port Count", min_value=0, max_value=576, value=default_port_count)
            port_type = st.selectbox("Port Type", ["LC", "SC", "RJ45", "SFP+", "QSFP", "Other"], index=["LC", "SC", "RJ45", "SFP+", "QSFP", "Other"].index(default_port_type) if default_port_type in ["LC", "SC", "RJ45", "SFP+", "QSFP", "Other"] else 0)
            prefix = st.text_input("Port Prefix", value=default_prefix)
            if role == "gpon_splitter_1x32":
                st.caption("Recommended splitter mapping: SP01 = input (feeder), SP02–SP33 = 32 subscriber outputs.")
            submitted = st.form_submit_button("Add Equipment", type="primary")
            if submitted:
                if not rack_id or not name:
                    st.error("Rack and name are required.")
                else:
                    device_id = next_int_id(st.session_state.devices, "device_id")
                    row = pd.DataFrame([{"device_id": device_id, "rack_id": rack_id, "name": name, "role": role, "position": position, "u_height": u_height, "port_count": port_count}])
                    st.session_state.devices = pd.concat([st.session_state.devices, row], ignore_index=True)
                    add_ports_for_device(device_id, port_count, prefix, port_type)
                    st.success(f"Added {name} with {port_count} ports.")
                    st.rerun()

    with tab3:
        st.subheader("Edit/Delete Equipment")
        st.data_editor(st.session_state.devices, use_container_width=True, num_rows="dynamic", key="devices_editor")
        if st.button("Save Equipment Changes"):
            st.session_state.devices = st.session_state.devices_editor
            st.success("Equipment saved.")
            st.rerun()
        if not st.session_state.devices.empty:
            del_id = st.selectbox("Delete equipment", st.session_state.devices["device_id"], format_func=device_label)
            if st.button("Delete Selected Equipment", type="secondary"):
                port_ids = ports_for_device(del_id)["port_id"].tolist()
                touched_cables = st.session_state.cables[
                    st.session_state.cables["a_port_id"].isin(port_ids) | st.session_state.cables["z_port_id"].isin(port_ids)
                ]
                if not touched_cables.empty:
                    st.error("This equipment has connected cables. Delete or move those cables first.")
                else:
                    st.session_state.ports = st.session_state.ports[~st.session_state.ports["port_id"].isin(port_ids)]
                    st.session_state.devices = st.session_state.devices[st.session_state.devices["device_id"] != del_id]
                    st.success("Equipment deleted.")
                    st.rerun()

# -----------------------------
# Connection Builder
# -----------------------------
elif page == "Connection Builder":
    st.header("Connection Builder")
    st.markdown("Build the **physical cable segment** first. Then attach it to a circuit/service.")

    tab1, tab2 = st.tabs(["Build Physical Connection", "Cable List / Edit"])
    with tab1:
        st.subheader("1) Select A-End")
        c1, c2 = st.columns(2)
        with c1:
            a_site = st.selectbox("A Site", st.session_state.sites["site_id"], format_func=lambda x: get_row("sites", "site_id", x)["name"], key="a_site")
            a_racks = st.session_state.racks[st.session_state.racks["site_id"] == a_site]
            a_rack = st.selectbox("A Rack", a_racks["rack_id"], format_func=lambda x: get_row("racks", "rack_id", x)["name"], key="a_rack") if not a_racks.empty else None
            a_devs = st.session_state.devices[st.session_state.devices["rack_id"] == a_rack] if a_rack else pd.DataFrame()
            a_dev = st.selectbox("A Equipment", a_devs["device_id"], format_func=device_label, key="a_dev") if not a_devs.empty else None
            a_port = show_port_table(a_dev, key_prefix="a_builder") if a_dev else None
        with c2:
            st.subheader("2) Select Z-End")
            z_site = st.selectbox("Z Site", st.session_state.sites["site_id"], format_func=lambda x: get_row("sites", "site_id", x)["name"], key="z_site")
            z_racks = st.session_state.racks[st.session_state.racks["site_id"] == z_site]
            z_rack = st.selectbox("Z Rack", z_racks["rack_id"], format_func=lambda x: get_row("racks", "rack_id", x)["name"], key="z_rack") if not z_racks.empty else None
            z_devs = st.session_state.devices[st.session_state.devices["rack_id"] == z_rack] if z_rack else pd.DataFrame()
            z_dev = st.selectbox("Z Equipment", z_devs["device_id"], format_func=device_label, key="z_dev") if not z_devs.empty else None
            z_port = show_port_table(z_dev, key_prefix="z_builder") if z_dev else None

        st.subheader("3) Cable Information")
        with st.form("create_cable_segment"):
            col1, col2, col3 = st.columns(3)
            cable_id = col1.text_input("Cable ID", value=f"CBL-{next_int_id(st.session_state.cables, 'index') if 'index' in st.session_state.cables.columns else len(st.session_state.cables)+1:04d}")
            cable_type = col2.selectbox("Cable Type", ["gpon_feeder", "gpon_distribution", "incoming_fiber", "fiber_patch", "ethernet_patch", "cross_connect", "carrier_handoff", "customer_handoff", "other"])
            color = col3.selectbox("Color", ["yellow", "blue", "orange", "aqua", "green", "white", "black", "other"])
            col4, col5, col6 = st.columns(3)
            strand = col4.text_input("Fiber / Pair / Strand", placeholder="F01, Blue tube/F12, Pair 1, etc.")
            length = col5.number_input("Length", min_value=0.0, value=3.0, step=0.5)
            project_location = col6.text_input("Project / Location", value="")
            notes = st.text_area("Notes")
            st.markdown("**Circuit Handling**")
            circuit_action = st.radio(
                "What should happen after this physical connection is created?",
                ["Auto-create new circuit", "Add to existing circuit", "Create named circuit", "Only create cable"],
                horizontal=False,
                help="For field mapping, Auto-create is usually best. You can merge multiple auto-created circuits later."
            )
            existing_circuit = None
            new_circuit_id = carrier_customer = service_type = bandwidth = status = None
            if circuit_action == "Add to existing circuit" and not st.session_state.circuits.empty:
                existing_circuit = st.selectbox("Existing Circuit", st.session_state.circuits["circuit_id"].astype(str).tolist())
            elif circuit_action == "Create named circuit":
                cA, cB, cC, cD = st.columns(4)
                new_circuit_id = cA.text_input("Circuit ID / Service ID")
                carrier_customer = cB.text_input("Carrier / Customer")
                service_type = cC.selectbox("Service Type", ["GPON", "DIA", "Transit", "Cross-Connect", "Wavelength", "MPLS", "Customer FTTH", "Internal", "Other"])
                bandwidth = cD.text_input("Bandwidth", placeholder="10G")
                status = st.selectbox("Status", ["active", "pending", "reserved", "decommissioned", "documented"])
            submit = st.form_submit_button("Create Physical Connection", type="primary")
            if submit:
                if not a_port or not z_port:
                    st.error("Select both A-End and Z-End ports.")
                elif str(a_port) == str(z_port):
                    st.error("A-End and Z-End cannot be the same port.")
                elif not cable_id:
                    st.error("Cable ID is required.")
                elif cable_id in st.session_state.cables["cable_id"].astype(str).tolist():
                    st.error("Cable ID already exists.")
                else:
                    new_cable = pd.DataFrame([{
                        "cable_id": cable_id, "site_id": a_site, "project_location": project_location,
                        "cable_type": cable_type, "color": color, "strand": strand,
                        "a_port_id": int(a_port), "z_port_id": int(z_port),
                        "a_description": port_label(a_port), "z_description": port_label(z_port),
                        "length": length, "notes": notes,
                    }])
                    st.session_state.cables = pd.concat([st.session_state.cables, new_cable], ignore_index=True)
                    if circuit_action == "Auto-create new circuit":
                        auto_id = create_auto_circuit_for_connection(int(a_port), int(z_port), cable_id, a_site, project_location, cable_type, notes)
                        st.success(f"Physical connection created and auto-circuit created: {auto_id}")
                    elif circuit_action == "Add to existing circuit" and existing_circuit:
                        add_cable_to_circuit(existing_circuit, cable_id, int(a_port), int(z_port))
                        st.success(f"Physical connection created and added to circuit: {existing_circuit}")
                    elif circuit_action == "Create named circuit" and new_circuit_id:
                        new_c = pd.DataFrame([{
                            "circuit_id": new_circuit_id, "site_id": a_site, "project_location": project_location,
                            "carrier_customer": carrier_customer, "service_type": service_type,
                            "bandwidth": bandwidth, "status": status,
                            "a_port_id": int(a_port), "z_port_id": int(z_port),
                            "cable_ids": [cable_id], "notes": notes or "Created from Connection Builder",
                        }])
                        st.session_state.circuits = pd.concat([st.session_state.circuits, new_c], ignore_index=True)
                        st.success(f"Physical connection created and named circuit created: {new_circuit_id}")
                    else:
                        st.success("Physical connection created. No circuit was created.")
                    st.rerun()

    with tab2:
        st.data_editor(st.session_state.cables, use_container_width=True, num_rows="dynamic", key="cables_editor")
        if st.button("Save Cable Changes"):
            st.session_state.cables = st.session_state.cables_editor
            st.success("Cables saved.")
            st.rerun()
        if not st.session_state.cables.empty:
            del_cable = st.selectbox("Delete cable", st.session_state.cables["cable_id"].astype(str).tolist())
            if st.button("Delete Selected Cable"):
                st.session_state.cables = st.session_state.cables[st.session_state.cables["cable_id"].astype(str) != del_cable]
                for idx in st.session_state.circuits.index:
                    ids = [x for x in safe_list(st.session_state.circuits.at[idx, "cable_ids"]) if str(x) != del_cable]
                    st.session_state.circuits.at[idx, "cable_ids"] = ids
                st.success("Cable deleted and removed from circuits.")
                st.rerun()

# -----------------------------
# Circuits
# -----------------------------
elif page == "Circuits":
    st.header("Circuits / Services")
    locations = ["All"] + sorted([x for x in st.session_state.circuits.get("project_location", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
    location = st.selectbox("Project / Location", locations)
    circuits_view = st.session_state.circuits.copy()
    if location != "All":
        circuits_view = circuits_view[circuits_view["project_location"].astype(str) == location]
    st.dataframe(circuits_view, use_container_width=True, hide_index=True)

    st.subheader("Create / Edit Circuits")
    tab1, tab2, tab3 = st.tabs(["Create Circuit from Existing Cable Path", "Edit/Delete", "Merge Circuits"])
    with tab1:
        with st.form("create_circuit_existing_path"):
            circuit_id = st.text_input("Circuit ID / Service ID")
            site_id = st.selectbox("Site", st.session_state.sites["site_id"], format_func=lambda x: get_row("sites", "site_id", x)["name"], key="circuit_site")
            project_location = st.text_input("Project / Location")
            carrier_customer = st.text_input("Carrier / Customer")
            service_type = st.selectbox("Service Type", ["GPON", "DIA", "Transit", "Cross-Connect", "Wavelength", "MPLS", "Customer FTTH", "Internal", "Other"])
            bandwidth = st.text_input("Bandwidth")
            status = st.selectbox("Status", ["active", "pending", "reserved", "decommissioned"])
            cable_ids = st.multiselect("Physical cable segments used by this circuit", st.session_state.cables["cable_id"].astype(str).tolist())
            start_port = end_port = None
            if cable_ids:
                candidate_ports = []
                subset = st.session_state.cables[st.session_state.cables["cable_id"].astype(str).isin(cable_ids)]
                for _, cb in subset.iterrows():
                    candidate_ports.extend([cb["a_port_id"], cb["z_port_id"]])
                candidate_ports = sorted(set([int(x) for x in candidate_ports if not pd.isna(x)]))
                start_port = st.selectbox("Circuit A-End Port", candidate_ports, format_func=port_label)
                end_port = st.selectbox("Circuit Z-End Port", candidate_ports, format_func=port_label)
            notes = st.text_area("Notes")
            if st.form_submit_button("Create Circuit", type="primary"):
                if not circuit_id:
                    st.error("Circuit ID is required.")
                elif circuit_id in st.session_state.circuits["circuit_id"].astype(str).tolist():
                    st.error("Circuit ID already exists.")
                else:
                    row = pd.DataFrame([{"circuit_id": circuit_id, "site_id": site_id, "project_location": project_location, "carrier_customer": carrier_customer, "service_type": service_type, "bandwidth": bandwidth, "status": status, "a_port_id": start_port, "z_port_id": end_port, "cable_ids": cable_ids, "notes": notes}])
                    st.session_state.circuits = pd.concat([st.session_state.circuits, row], ignore_index=True)
                    st.success("Circuit created.")
                    st.rerun()
    with tab2:
        st.data_editor(st.session_state.circuits, use_container_width=True, num_rows="dynamic", key="circuits_editor")
        if st.button("Save Circuit Changes"):
            st.session_state.circuits = st.session_state.circuits_editor
            st.success("Circuits saved.")
            st.rerun()
        if not st.session_state.circuits.empty:
            del_circuit = st.selectbox("Delete circuit", st.session_state.circuits["circuit_id"].astype(str).tolist())
            if st.button("Delete Selected Circuit"):
                st.session_state.circuits = st.session_state.circuits[st.session_state.circuits["circuit_id"].astype(str) != del_circuit]
                st.success("Circuit deleted. Physical cables were kept.")
                st.rerun()

    with tab3:
        st.subheader("Merge Physical Connections into One Circuit")
        st.markdown("Use this after mapping several individual patch cables. Pick the real circuit/service as the target, then merge the auto-created connection circuits into it.")
        if st.session_state.circuits.empty:
            st.info("No circuits to merge yet.")
        else:
            all_circuits = st.session_state.circuits["circuit_id"].astype(str).tolist()
            target = st.selectbox("Target circuit to keep", all_circuits, key="merge_target")
            sources = st.multiselect(
                "Circuits/connections to merge into the target",
                [c for c in all_circuits if c != target],
                key="merge_sources",
            )
            delete_sources = st.checkbox("Delete merged source circuit records after merge", value=True)
            if target:
                target_row = st.session_state.circuits[st.session_state.circuits["circuit_id"].astype(str) == target].iloc[0]
                st.caption(f"Target currently has {len(safe_list(target_row.get('cable_ids', [])))} cable segment(s).")
            if sources:
                preview = st.session_state.circuits[st.session_state.circuits["circuit_id"].astype(str).isin(sources)]
                st.dataframe(preview[["circuit_id", "carrier_customer", "service_type", "status", "cable_ids"]], use_container_width=True, hide_index=True)
            if st.button("Merge Selected Circuits", type="primary"):
                if not sources:
                    st.error("Select at least one source circuit to merge.")
                else:
                    merged = merge_circuits(target, sources, delete_sources=delete_sources)
                    st.success(f"Merged {len(merged)} circuit(s) into {target}.")
                    st.rerun()

# -----------------------------
# Trace / Search
# -----------------------------
elif page == "Trace / Search":
    st.header("Trace / Search")
    search = st.text_input("Search customer, circuit, cable, port, equipment, street, pole, or notes")
    if search:
        s = search.lower()
        cable_matches = st.session_state.cables[st.session_state.cables.astype(str).apply(lambda r: r.str.lower().str.contains(s, na=False).any(), axis=1)]
        circuit_matches = st.session_state.circuits[st.session_state.circuits.astype(str).apply(lambda r: r.str.lower().str.contains(s, na=False).any(), axis=1)]
        device_matches = st.session_state.devices[st.session_state.devices.astype(str).apply(lambda r: r.str.lower().str.contains(s, na=False).any(), axis=1)]
        st.subheader("Matching Circuits")
        st.dataframe(circuit_matches, use_container_width=True, hide_index=True)
        st.subheader("Matching Cables")
        st.dataframe(cable_matches, use_container_width=True, hide_index=True)
        st.subheader("Matching Equipment")
        st.dataframe(device_matches, use_container_width=True, hide_index=True)

    if not st.session_state.circuits.empty:
        st.subheader("Trace Circuit Path")
        circuit_id = st.selectbox("Circuit", st.session_state.circuits["circuit_id"].astype(str).tolist())
        circuit = st.session_state.circuits[st.session_state.circuits["circuit_id"].astype(str) == circuit_id].iloc[0]
        st.markdown(f"**{circuit['circuit_id']}** — {circuit.get('carrier_customer','')} — {circuit.get('bandwidth','')} — {circuit.get('status','')}")
        cable_ids = safe_list(circuit.get("cable_ids", []))
        if not cable_ids and circuit.get("a_port_id") and circuit.get("z_port_id"):
            path = find_path(circuit["a_port_id"], circuit["z_port_id"])
            cable_ids = [x[2] for x in path]
        if not cable_ids:
            st.warning("No physical cable path is assigned to this circuit yet.")
        else:
            for i, cable_id in enumerate(cable_ids, start=1):
                cable = get_row("cables", "cable_id", cable_id)
                if cable is None:
                    continue
                a = endpoint_details(cable.get("a_port_id"), cable.get("a_description", ""))
                z = endpoint_details(cable.get("z_port_id"), cable.get("z_description", ""))
                st.markdown(
                    f"""
                    <div class="path-hop">
                      <div style="display:flex; justify-content:space-between; gap:12px; align-items:center;">
                        <div>
                          <b>Hop {i}: {cable['cable_id']}</b> — {cable['cable_type']}
                          <span class="subtle"> {cable.get('color','')} {cable.get('strand','')}</span>
                        </div>
                        <div class="subtle">{cable.get('project_location','')}</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                col_a, col_mid, col_z = st.columns([5, 1, 5])
                with col_a:
                    st.markdown(endpoint_card("A-END", a), unsafe_allow_html=True)
                with col_mid:
                    st.markdown("<div style='text-align:center; font-size:2rem; padding-top:34px;'>➡️</div>", unsafe_allow_html=True)
                with col_z:
                    st.markdown(endpoint_card("Z-END", z), unsafe_allow_html=True)

                st.dataframe(pd.DataFrame([{
                    "Cable": cable["cable_id"],
                    "Type": cable["cable_type"],
                    "A-End Device/Panel": a["equipment"],
                    "A-End Rack": a["rack"],
                    "A-End Port": a["port"],
                    "Z-End Device/Panel": z["equipment"],
                    "Z-End Rack": z["rack"],
                    "Z-End Port": z["port"],
                    "Notes": cable.get("notes", ""),
                }]), use_container_width=True, hide_index=True)


# -----------------------------
# Patchmanager-style View
# -----------------------------
elif page == "Patchmanager View":
    st.header("Patchmanager-Style Physical Layer View")
    st.caption("Pick a location, rack, and equipment. Then see port availability, existing circuits, and build a connection from that same screen.")

    left, mid, right = st.columns([1.1, 1.35, 1.35])
    with left:
        st.markdown('<div class="pm-panel"><div class="pm-header">Location Tree</div>', unsafe_allow_html=True)
        site_id = st.selectbox("Site", st.session_state.sites["site_id"], format_func=lambda x: get_row("sites", "site_id", x)["name"], key="pm_site")
        rack_options = st.session_state.racks[st.session_state.racks["site_id"] == site_id]
        if rack_options.empty:
            st.info("No racks for this site.")
            st.markdown('</div>', unsafe_allow_html=True)
            st.stop()
        rack_id = st.selectbox("Rack", rack_options["rack_id"], format_func=lambda x: get_row("racks", "rack_id", x)["name"], key="pm_rack")
        devs = st.session_state.devices[st.session_state.devices["rack_id"] == rack_id].sort_values("position")
        if devs.empty:
            st.info("No equipment in this rack.")
            st.markdown('</div>', unsafe_allow_html=True)
            st.stop()
        device_id = st.selectbox("Equipment / Patch Panel", devs["device_id"], format_func=device_label, key="pm_device")
        st.markdown("**Rack Equipment**")
        for _, d in devs.iterrows():
            start = int(d["position"]); end = start + int(d["u_height"]) - 1
            marker = "▶ " if str(d["device_id"]) == str(device_id) else ""
            st.write(f"{marker}U{start}–U{end}: {d['name']}")
        st.markdown('</div>', unsafe_allow_html=True)

    with mid:
        st.markdown('<div class="pm-panel"><div class="pm-header">Ports and Existing Circuits</div>', unsafe_allow_html=True)
        st.subheader(device_label(device_id))
        selected_port = show_port_chips(device_id, title="Port Map")
        if selected_port:
            details = endpoint_details(selected_port)
            st.markdown(endpoint_card("Selected Port", details), unsafe_allow_html=True)
            conn_df = port_connection_rows(selected_port)
            if conn_df.empty:
                st.success("This port is available for a new connection/circuit.")
            else:
                st.warning("This port is already connected.")
                st.dataframe(conn_df, use_container_width=True, hide_index=True)
                circuit_choices = sorted(set(",".join(conn_df["Circuit(s)"].astype(str)).replace(", ", ",").split(",")))
                circuit_choices = [c for c in circuit_choices if c]
                if circuit_choices:
                    st.session_state.pm_selected_circuit = st.selectbox("Open existing circuit", circuit_choices, key="pm_open_circuit")
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="pm-panel"><div class="pm-header">Quick Build Connection</div>', unsafe_allow_html=True)
        st.caption("Use this to document an existing patch cable or incoming connection from the selected port.")
        if selected_port:
            st.write(f"**A-End:** {port_label(selected_port)}")
            z_rack = st.selectbox("Z Rack", rack_options["rack_id"], format_func=lambda x: get_row("racks", "rack_id", x)["name"], key="pm_z_rack")
            z_devs = st.session_state.devices[st.session_state.devices["rack_id"] == z_rack]
            z_dev = st.selectbox("Z Equipment", z_devs["device_id"], format_func=device_label, key="pm_z_dev") if not z_devs.empty else None
            z_port = show_port_chips(z_dev, title="Z-End Port Map") if z_dev else None
            with st.form("pm_quick_connect"):
                default_cable = f"PATCH-{len(st.session_state.cables)+1:04d}"
                cable_id = st.text_input("Cable ID", value=default_cable)
                cable_type = st.selectbox("Cable Type", ["gpon_feeder", "gpon_distribution", "fiber_patch", "ethernet_patch", "incoming_fiber", "cross_connect", "carrier_handoff", "customer_handoff", "other"], key="pm_cable_type")
                project_location = st.text_input("Project / Location", key="pm_project")
                circuit_mode = st.radio("Circuit", ["Auto-create circuit", "Add to existing circuit", "Create named circuit"], key="pm_circuit_mode")
                existing_circuit = None
                named_id = ""
                carrier_customer = ""
                bandwidth = ""
                if circuit_mode == "Add to existing circuit" and not st.session_state.circuits.empty:
                    existing_circuit = st.selectbox("Existing circuit", st.session_state.circuits["circuit_id"].astype(str).tolist(), key="pm_existing_circuit")
                if circuit_mode == "Create named circuit":
                    named_id = st.text_input("Circuit ID / Service ID", key="pm_named_circuit")
                    carrier_customer = st.text_input("Carrier / Customer", key="pm_carrier")
                    bandwidth = st.text_input("Bandwidth", key="pm_bandwidth")
                notes = st.text_area("Notes", key="pm_notes")
                if st.form_submit_button("Create Connection", type="primary"):
                    if not z_port or str(selected_port) == str(z_port):
                        st.error("Select a different Z-End port.")
                    elif cable_id in st.session_state.cables["cable_id"].astype(str).tolist():
                        st.error("Cable ID already exists.")
                    else:
                        new_cable = pd.DataFrame([{"cable_id": cable_id, "site_id": site_id, "project_location": project_location, "cable_type": cable_type, "color": "", "strand": "", "a_port_id": int(selected_port), "z_port_id": int(z_port), "a_description": port_label(selected_port), "z_description": port_label(z_port), "length": 0, "notes": notes}])
                        st.session_state.cables = pd.concat([st.session_state.cables, new_cable], ignore_index=True)
                        if circuit_mode == "Add to existing circuit" and existing_circuit:
                            add_cable_to_circuit(existing_circuit, cable_id, int(selected_port), int(z_port))
                            st.session_state.pm_selected_circuit = existing_circuit
                            st.success(f"Connection added to {existing_circuit}.")
                        elif circuit_mode == "Create named circuit" and named_id:
                            st.session_state.circuits = pd.concat([st.session_state.circuits, pd.DataFrame([{"circuit_id": named_id, "site_id": site_id, "project_location": project_location, "carrier_customer": carrier_customer, "service_type": "Cross-Connect", "bandwidth": bandwidth, "status": "documented", "a_port_id": int(selected_port), "z_port_id": int(z_port), "cable_ids": [cable_id], "notes": notes}])], ignore_index=True)
                            st.session_state.pm_selected_circuit = named_id
                            st.success(f"Connection and circuit {named_id} created.")
                        else:
                            auto_id = create_auto_circuit_for_connection(int(selected_port), int(z_port), cable_id, site_id, project_location, cable_type, notes)
                            st.session_state.pm_selected_circuit = auto_id
                            st.success(f"Connection and auto circuit {auto_id} created.")
                        st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    selected_circuit = st.session_state.get("pm_selected_circuit")
    if selected_circuit:
        show_circuit_path_diagram(selected_circuit)

# -----------------------------
# Work Orders
# -----------------------------
elif page == "Work Orders":
    st.header("Moves, Adds, and Changes")
    st.caption("Lightweight work orders like Patchmanager-style MAC tracking.")
    with st.form("new_work_order"):
        c1, c2, c3 = st.columns(3)
        wo_type = c1.selectbox("Type", ["Move", "Add", "Change", "Disconnect", "Audit"])
        site_id = c2.selectbox("Site", st.session_state.sites["site_id"], format_func=lambda x: get_row("sites", "site_id", x)["name"], key="wo_site")
        status = c3.selectbox("Status", ["open", "planned", "in_progress", "complete", "cancelled"])
        circuit_id = st.selectbox("Related Circuit", [""] + st.session_state.circuits["circuit_id"].astype(str).tolist()) if not st.session_state.circuits.empty else ""
        assigned_to = st.text_input("Assigned To")
        description = st.text_area("Work Description")
        notes = st.text_area("Notes")
        if st.form_submit_button("Create Work Order", type="primary"):
            wo_id = f"WO-{len(st.session_state.work_orders)+1:05d}"
            row = pd.DataFrame([{"wo_id": wo_id, "created": datetime.now().strftime("%Y-%m-%d %H:%M"), "type": wo_type, "status": status, "site_id": site_id, "description": description, "circuit_id": circuit_id, "assigned_to": assigned_to, "notes": notes}])
            st.session_state.work_orders = pd.concat([st.session_state.work_orders, row], ignore_index=True)
            st.success(f"Created {wo_id}.")
            st.rerun()
    st.data_editor(st.session_state.work_orders, use_container_width=True, num_rows="dynamic", key="wo_editor")
    if st.button("Save Work Orders"):
        st.session_state.work_orders = st.session_state.wo_editor
        st.success("Work orders saved.")
        st.rerun()

# -----------------------------
# Reports
# -----------------------------
elif page == "Reports":
    st.header("Reports")
    st.subheader("Equipment / Patch Panel Utilization")
    util = equipment_utilization_df()
    st.dataframe(util, use_container_width=True, hide_index=True)
    st.download_button("Download Utilization CSV", util.to_csv(index=False), file_name="equipment_utilization.csv", mime="text/csv")

    st.subheader("Cable Inventory")
    st.dataframe(st.session_state.cables, use_container_width=True, hide_index=True)
    st.download_button("Download Cable Inventory CSV", st.session_state.cables.to_csv(index=False), file_name="cable_inventory.csv", mime="text/csv")

    st.subheader("Circuit Inventory")
    st.dataframe(st.session_state.circuits, use_container_width=True, hide_index=True)
    st.download_button("Download Circuit Inventory CSV", st.session_state.circuits.to_csv(index=False), file_name="circuit_inventory.csv", mime="text/csv")

    st.subheader("Data Quality Checks")
    quality = data_quality_report()
    st.dataframe(quality, use_container_width=True, hide_index=True)
    issues = quality[quality["Severity"].isin(["high", "medium"])]["Count"].sum()
    if issues:
        st.warning(f"Found {int(issues)} issue(s). Review the checks before exporting or sharing inventory data.")
    else:
        st.success("No data quality issues detected in the basic consistency checks.")
    st.download_button("Download Data Quality Report CSV", quality.to_csv(index=False), file_name="data_quality_report.csv", mime="text/csv")

# -----------------------------
# Import TAP Sheet
# -----------------------------
elif page == "Import TAP Sheet":
    st.header("Import TAP / Customer Fiber Sheet")
    st.markdown("Expected columns: `Tap`, `PORT`, `Cable`, `Customer`, `CO Fiber`, `Pole`, `Street`.")
    uploaded = st.file_uploader("Upload Excel file", type=["xlsx", "xls"])
    mode = st.radio("Import into", ["Existing Site", "Create New Site"], horizontal=True)
    if mode == "Existing Site":
        site_id = st.selectbox("Site", st.session_state.sites["site_id"], format_func=lambda x: get_row("sites", "site_id", x)["name"])
    else:
        new_site_name = st.text_input("New Site Name")
        new_site_address = st.text_input("New Site Address")
        site_id = None
    project_location = st.text_input("Project / Location Name", placeholder="Example: Oakfield TAP Import")
    if uploaded:
        df = normalize_import_columns(pd.read_excel(uploaded))
        st.subheader("Preview")
        st.dataframe(df.head(25), use_container_width=True, hide_index=True)
        if st.button("Import TAP Records", type="primary"):
            if mode == "Create New Site":
                if not new_site_name:
                    st.error("New site name is required.")
                    st.stop()
                site_id = next_int_id(st.session_state.sites, "site_id")
                st.session_state.sites = pd.concat([st.session_state.sites, pd.DataFrame([{"site_id": site_id, "name": new_site_name, "address": new_site_address, "notes": "Imported TAP project"}])], ignore_index=True)
            required = ["Tap", "PORT", "Cable", "Customer", "CO Fiber", "Pole", "Street"]
            missing = [c for c in required if c not in df.columns]
            if missing:
                st.error(f"Missing required columns: {missing}")
                st.caption(f"Detected columns: {', '.join(map(str, df.columns.tolist()))}")
            else:
                rows = []
                circuits = []
                for idx, r in df.iterrows():
                    cable_id = f"{r['Cable']}-{r['Tap']}-{r['PORT']}".replace(" ", "_")
                    rows.append({
                        "cable_id": cable_id,
                        "site_id": site_id,
                        "project_location": project_location,
                        "cable_type": "customer_tap_fiber",
                        "color": "",
                        "strand": r["CO Fiber"],
                        "a_port_id": None,
                        "z_port_id": None,
                        "a_description": f"CO Fiber {r['CO Fiber']}",
                        "z_description": f"TAP {r['Tap']} Port {r['PORT']}",
                        "length": None,
                        "notes": f"Customer: {r['Customer']} | Pole: {r['Pole']} | Street: {r['Street']}",
                    })
                    circuits.append({
                        "circuit_id": f"TAP-{r['Tap']}-P{r['PORT']}-{idx+1}",
                        "site_id": site_id,
                        "project_location": project_location,
                        "carrier_customer": str(r["Customer"]),
                        "service_type": "Customer FTTH",
                        "bandwidth": "",
                        "status": "documented",
                        "a_port_id": None,
                        "z_port_id": None,
                        "cable_ids": [cable_id],
                        "notes": f"Cable {r['Cable']} | CO Fiber {r['CO Fiber']} | Pole {r['Pole']} | Street {r['Street']}",
                    })
                st.session_state.cables = pd.concat([st.session_state.cables, pd.DataFrame(rows)], ignore_index=True)
                st.session_state.circuits = pd.concat([st.session_state.circuits, pd.DataFrame(circuits)], ignore_index=True)
                st.success(f"Imported {len(rows)} TAP/customer fiber records into {project_location}.")
                st.rerun()
