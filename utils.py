import pandas as pd
import streamlit as st
from models import used_port_ids, port_label, circuits_for_port


def role_icon(role):
    role = str(role).lower()
    if "fiber" in role:
        return "🧵"
    if "ethernet" in role:
        return "🔌"
    if "network" in role or "switch" in role or "router" in role:
        return "🖧"
    if "tap" in role:
        return "🏠"
    return "📦"


def rack_block_view(rack_id, selected_device_id=None, selected_circuit_id=None):
    racks = st.session_state.racks
    devices = st.session_state.devices[st.session_state.devices["rack_id"] == rack_id].copy()
    rack = racks[racks["rack_id"] == rack_id].iloc[0]
    st.markdown(f"### Rack {rack['name']} — {rack['room']} ({int(rack['u_height'])}U)")
    if devices.empty:
        st.info("No equipment in this rack yet.")
        return
    devices = devices.sort_values("position")
    used = used_port_ids()
    for _, dev in devices.iterrows():
        ports = st.session_state.ports[st.session_state.ports["device_id"] == int(dev["device_id"])]
        used_count = len([p for p in ports["port_id"].tolist() if p in used])
        total = len(ports)
        start = int(dev["position"])
        end = start + int(dev["u_height"]) - 1
        highlight = "selected-device" if int(dev["device_id"]) == selected_device_id else ""
        label = f"{role_icon(dev['role'])} {dev['name']}"
        st.markdown(
            f"""
            <div class="equip-card {highlight}">
                <div class="equip-u">U{start}–U{end}</div>
                <div class="equip-main">
                    <div class="equip-title">{label}</div>
                    <div class="equip-meta">{dev['role']} • {used_count}/{total} used • {total-used_count} available</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def inject_css():
    st.markdown(
        """
        <style>
        .equip-card{display:flex;align-items:center;border:1px solid #d8dee9;border-radius:12px;padding:10px 12px;margin:7px 0;background:#ffffff;box-shadow:0 1px 2px rgba(0,0,0,.05)}
        .equip-card.selected-device{border:2px solid #2563eb;background:#eff6ff}
        .equip-u{width:82px;font-weight:700;color:#334155;font-size:15px}
        .equip-title{font-weight:800;font-size:16px;color:#0f172a}
        .equip-meta{font-size:13px;color:#64748b;margin-top:2px}
        .port-used{background:#fff7ed;border:1px solid #fdba74;border-radius:10px;padding:8px;margin:4px 0}
        .port-free{background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:8px;margin:4px 0}
        .path-card{background:#f8fafc;border:1px solid #cbd5e1;border-radius:14px;padding:14px;margin:8px 0}
        .big-arrow{text-align:center;font-size:26px;font-weight:800;color:#2563eb}
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_device_ports(device_id):
    dev = st.session_state.devices[st.session_state.devices["device_id"] == device_id].iloc[0]
    ports = st.session_state.ports[st.session_state.ports["device_id"] == device_id].copy()
    used = used_port_ids()
    st.subheader(f"Ports — {dev['name']}")
    if ports.empty:
        st.info("This equipment has no ports yet.")
        return
    ports["status"] = ports["port_id"].apply(lambda x: "USED" if x in used else "AVAILABLE")
    chosen = st.selectbox(
        "Select a port",
        ports["port_id"].tolist(),
        format_func=lambda pid: f"{ports[ports['port_id']==pid].iloc[0]['name']} — {ports[ports['port_id']==pid].iloc[0]['status']}",
        key=f"port_select_{device_id}",
    )
    p = ports[ports["port_id"] == chosen].iloc[0]
    if chosen in used:
        st.warning(f"{p['name']} is already used.")
        c = st.session_state.cables[(st.session_state.cables["a_port_id"] == chosen) | (st.session_state.cables["z_port_id"] == chosen)]
        if not c.empty:
            st.write("Connected cable(s):")
            c2 = c.copy()
            c2["A-End"] = c2["a_port_id"].apply(port_label)
            c2["Z-End"] = c2["z_port_id"].apply(port_label)
            st.dataframe(c2[["cable_id", "cable_type", "strand", "A-End", "Z-End"]], use_container_width=True)
        circs = circuits_for_port(chosen)
        if not circs.empty:
            st.write("Existing circuit(s):")
            st.dataframe(circs[["circuit_id", "customer", "tap", "tap_port", "co_fiber", "status", "street", "pole"]], use_container_width=True)
    else:
        st.success(f"{p['name']} is available.")
    col1, col2 = st.columns(2)
    if col1.button("Use as A-End", key=f"a_{chosen}"):
        st.session_state.pending_a_port = int(chosen)
        st.success(f"A-End set: {port_label(chosen)}")
    if col2.button("Use as Z-End", key=f"z_{chosen}"):
        st.session_state.pending_z_port = int(chosen)
        st.success(f"Z-End set: {port_label(chosen)}")


def show_circuit_path(circuit_id):
    circs = st.session_state.circuits
    match = circs[circs["circuit_id"].astype(str) == str(circuit_id)]
    if match.empty:
        st.info("No circuit selected.")
        return
    c = match.iloc[0]
    st.markdown(f"### Circuit Path — {c['circuit_id']}")
    st.markdown(f"**Customer:** {c.get('customer','')}  ")
    ids = c.get("cable_ids", [])
    if not isinstance(ids, list):
        ids = [x.strip() for x in str(ids).replace("[", "").replace("]", "").replace("'", "").split(",") if x.strip()]
    if not ids:
        st.warning("This circuit has no cable segments assigned.")
        return
    for cid in ids:
        cable = st.session_state.cables[st.session_state.cables["cable_id"].astype(str) == str(cid)]
        if cable.empty:
            continue
        cable = cable.iloc[0]
        st.markdown(
            f"""
            <div class="path-card">
                <b>{cable['cable_id']}</b> • {cable.get('cable_type','')} • strand/fiber {cable.get('strand','') or '—'}<br>
                {port_label(cable.get('a_port_id'))}<div class="big-arrow">↓</div>{port_label(cable.get('z_port_id'))}
            </div>
            """,
            unsafe_allow_html=True,
        )
