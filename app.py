import ast
from datetime import datetime
import pandas as pd
import streamlit as st
from models import initialize_data, ensure_ports_for_device, port_label, used_port_ids
from utils import inject_css, rack_block_view, show_device_ports, show_circuit_path

st.set_page_config(page_title="Colo + TAP Fiber Tracker", layout="wide", page_icon="🧵")
initialize_data()
inject_css()

st.title("🧵 Colocation Cable, Circuit & TAP Fiber Tracker")

page = st.sidebar.selectbox(
    "Navigation",
    [
        "🏠 Dashboard",
        "🗺️ TAP / Customer Fiber Map",
        "🧱 Rack & Equipment View",
        "🔌 Build Cable / Circuit",
        "📋 Cables",
        "📡 Circuits",
        "⚙️ Manage Racks & Equipment",
    ],
)


def normalize_tap_import(df, project="", location=""):
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in ["tap", "tap #", "tap number"]:
            rename[col] = "tap"
        elif key in ["port", "tap port", "port on tap"]:
            rename[col] = "tap_port"
        elif key == "cable":
            rename[col] = "cable"
        elif key == "customer":
            rename[col] = "customer"
        elif key in ["co fiber", "cofiber", "co_fiber"]:
            rename[col] = "co_fiber"
        elif key == "pole":
            rename[col] = "pole"
        elif key == "street":
            rename[col] = "street"
    df = df.rename(columns=rename)
    needed = ["tap", "tap_port", "cable", "customer", "co_fiber", "pole", "street"]
    for col in needed:
        if col not in df.columns:
            df[col] = None
    df = df[needed].copy()
    df = df.dropna(how="all")
    for col in needed:
        df[col] = df[col].apply(lambda x: "" if pd.isna(x) else str(x).strip())
    df["circuit_id"] = df.apply(lambda r: f"TAP-{r['tap']}-P{str(r['tap_port']).zfill(2)}", axis=1)
    df["status"] = df["customer"].apply(lambda x: "available" if x == "" or x.lower() in ["nan", "none"] else "assigned")
    df["project"] = project
    df["location"] = location
    return df


def get_or_create_tap_device(tap, site_id=1):
    name = f"TAP-{tap}"
    rack_name = f"{get_site_name(site_id)}-OSP-TAP-Inventory"
    rack_id = get_or_create_site_rack(site_id, "OSP", rack_name)
    devices = st.session_state.devices
    found = devices[(devices["rack_id"] == rack_id) & (devices["name"] == name)]
    if not found.empty:
        return int(found.iloc[0]["device_id"])
    new_id = int(devices["device_id"].max() + 1) if not devices.empty else 1
    next_pos = min(len(devices[devices["rack_id"] == rack_id]) + 1, 42)
    new = pd.DataFrame([{
        "device_id": new_id, "rack_id": rack_id, "name": name,
        "role": "tap_terminal_access_port", "position": next_pos,
        "u_height": 1, "port_count": 8, "port_prefix": "P",
    }])
    st.session_state.devices = pd.concat([devices, new], ignore_index=True)
    ensure_ports_for_device(new_id)
    return new_id


def find_tap_port_id(tap_device_id, tap_port):
    ports = st.session_state.ports[st.session_state.ports["device_id"] == tap_device_id].copy()
    if ports.empty:
        return None
    try:
        idx = int(float(str(tap_port)))
    except Exception:
        idx = 1
    idx = max(1, min(idx, len(ports)))
    return int(ports.iloc[idx - 1]["port_id"])


def find_co_port_id(co_fiber, site_id=1):
    co_dev_id = get_or_create_site_device(
        site_id=site_id, name="CO-Fiber-Panel-01", role="fiber_patch_panel",
        rack_room="CO", rack_suffix="CO-R01", position=1, u_height=4,
        port_count=288, port_prefix="COF",
    )
    ports = st.session_state.ports[st.session_state.ports["device_id"] == int(co_dev_id)]
    if ports.empty:
        return None
    try:
        idx = int(float(str(co_fiber)))
    except Exception:
        idx = 1
    idx = max(1, min(idx, len(ports)))
    return int(ports.iloc[idx - 1]["port_id"])


def create_tap_circuits_from_records(records, site_id=1, site_name=""):
    added_cables = 0
    added_circuits = 0
    for _, r in records.iterrows():
        if not r["tap"] or not r["tap_port"]:
            continue
        tap_dev = get_or_create_tap_device(r["tap"], site_id=site_id)
        tap_port_id = find_tap_port_id(tap_dev, r["tap_port"])
        co_port_id = find_co_port_id(r["co_fiber"], site_id=site_id)
        cable_id = f"{r['cable']}-TAP{r['tap']}-P{str(r['tap_port']).zfill(2)}".replace(" ", "-")
        if st.session_state.cables[st.session_state.cables["cable_id"] == cable_id].empty:
            cable_row = pd.DataFrame([{
                "cable_id": cable_id,
                "cable_type": "fiber",
                "color": "yellow",
                "fiber_count": 1,
                "subtype": "tap_drop_or_distribution",
                "a_port_id": co_port_id,
                "z_port_id": tap_port_id,
                "a_description": f"CO Fiber {r['co_fiber']}",
                "z_description": f"TAP {r['tap']} Port {r['tap_port']}",
                "length": None,
                "strand": r["co_fiber"],
                "site_id": site_id,
                "site_name": site_name or get_site_name(site_id),
                "project": r.get("project", ""),
                "location": r.get("location", ""),
                "site_id": site_id,
                "site_name": site_name or get_site_name(site_id),
            }])
            st.session_state.cables = pd.concat([st.session_state.cables, cable_row], ignore_index=True)
            added_cables += 1
        circuit_id = r["circuit_id"]
        if st.session_state.circuits[st.session_state.circuits["circuit_id"] == circuit_id].empty:
            circuit_row = pd.DataFrame([{
                "circuit_id": circuit_id,
                "carrier": "Pioneer",
                "circuit_type": "Customer Fiber / TAP",
                "bandwidth": "",
                "status": r["status"],
                "a_end": f"CO Fiber {r['co_fiber']}",
                "z_end": f"TAP {r['tap']} Port {r['tap_port']}",
                "cable_ids": [cable_id],
                "notes": f"Pole {r['pole']} / {r['street']} / Cable {r['cable']}",
                "customer": r["customer"],
                "tap": r["tap"],
                "tap_port": r["tap_port"],
                "co_fiber": r["co_fiber"],
                "street": r["street"],
                "pole": r["pole"],
                "project": r.get("project", ""),
                "location": r.get("location", ""),
            }])
            st.session_state.circuits = pd.concat([st.session_state.circuits, circuit_row], ignore_index=True)
            added_circuits += 1
    return added_cables, added_circuits


def circuit_ids_touching_device(device_id):
    ports = st.session_state.ports[st.session_state.ports["device_id"] == device_id]["port_id"].tolist()
    if not ports or st.session_state.cables.empty:
        return []
    cable_ids = st.session_state.cables[
        st.session_state.cables["a_port_id"].isin(ports) | st.session_state.cables["z_port_id"].isin(ports)
    ]["cable_id"].astype(str).tolist()
    if not cable_ids or st.session_state.circuits.empty:
        return []
    out = []
    for _, c in st.session_state.circuits.iterrows():
        ids = c.get("cable_ids", [])
        if not isinstance(ids, list):
            try:
                ids = ast.literal_eval(str(ids))
            except Exception:
                ids = [str(ids)]
        if any(str(x) in cable_ids for x in ids):
            out.append(c["circuit_id"])
    return out


def get_site_name(site_id):
    sites = st.session_state.sites
    match = sites[sites["site_id"] == int(site_id)]
    return match.iloc[0]["name"] if not match.empty else f"Site {site_id}"


def create_site(name, address=""):
    name = str(name).strip()
    if not name:
        return None
    existing = st.session_state.sites[st.session_state.sites["name"].astype(str).str.lower() == name.lower()]
    if not existing.empty:
        return int(existing.iloc[0]["site_id"])
    new_id = int(st.session_state.sites["site_id"].max() + 1) if not st.session_state.sites.empty else 1
    st.session_state.sites = pd.concat([st.session_state.sites, pd.DataFrame([{
        "site_id": new_id, "name": name, "address": address
    }])], ignore_index=True)
    return new_id


def get_or_create_site_rack(site_id, room, rack_name, u_height=42):
    racks = st.session_state.racks
    found = racks[(racks["site_id"] == int(site_id)) & (racks["name"].astype(str) == str(rack_name))]
    if not found.empty:
        return int(found.iloc[0]["rack_id"])
    new_id = int(racks["rack_id"].max() + 1) if not racks.empty else 1
    st.session_state.racks = pd.concat([racks, pd.DataFrame([{
        "rack_id": new_id, "site_id": int(site_id), "room": room, "name": rack_name, "u_height": u_height
    }])], ignore_index=True)
    return new_id


def get_or_create_site_device(site_id, name, role, rack_room, rack_suffix, position, u_height, port_count, port_prefix):
    rack_name = f"{get_site_name(site_id)}-{rack_suffix}"
    rack_id = get_or_create_site_rack(site_id, rack_room, rack_name)
    devices = st.session_state.devices
    found = devices[(devices["rack_id"] == rack_id) & (devices["name"].astype(str) == str(name))]
    if not found.empty:
        return int(found.iloc[0]["device_id"])
    new_id = int(devices["device_id"].max() + 1) if not devices.empty else 1
    st.session_state.devices = pd.concat([devices, pd.DataFrame([{
        "device_id": new_id, "rack_id": rack_id, "name": name, "role": role,
        "position": position, "u_height": u_height, "port_count": port_count, "port_prefix": port_prefix,
    }])], ignore_index=True)
    ensure_ports_for_device(new_id)
    return new_id


def ensure_site_columns():
    for df_name in ["tap_records", "circuits", "cables"]:
        if df_name in st.session_state:
            for col in ["site_id", "site_name", "project", "location"]:
                if col not in st.session_state[df_name].columns:
                    st.session_state[df_name][col] = ""
    if "change_log" not in st.session_state:
        st.session_state.change_log = pd.DataFrame(columns=[
            "timestamp", "event_type", "entity", "entity_id", "details",
        ])


def log_event(event_type, entity, entity_id, details):
    row = pd.DataFrame([{
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        "event_type": event_type,
        "entity": entity,
        "entity_id": str(entity_id),
        "details": str(details),
    }])
    st.session_state.change_log = pd.concat([st.session_state.change_log, row], ignore_index=True)


def endpoint_label(endpoint_type, port_id, description):
    if endpoint_type == "device_port":
        return port_label(port_id)
    return str(description).strip() if str(description).strip() else "External / Unknown"


def normalize_cable_id_list(value):
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if value is None or pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            out = ast.literal_eval(text)
            if isinstance(out, list):
                return [str(x).strip() for x in out if str(x).strip()]
        except Exception:
            pass
    return [x.strip() for x in text.replace(";", ",").split(",") if x.strip()]


ensure_site_columns()

if page == "🏠 Dashboard":
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Sites", len(st.session_state.sites))
    col2.metric("Racks", len(st.session_state.racks))
    col3.metric("Equipment", len(st.session_state.devices))
    col4.metric("Cables", len(st.session_state.cables))
    col5.metric("Circuits", len(st.session_state.circuits))
    if not st.session_state.cables.empty:
        with st.container(border=True):
            st.subheader("Cable Inventory Summary")
            subtype_counts = st.session_state.cables["subtype"].fillna("unknown").astype(str).value_counts().reset_index()
            subtype_counts.columns = ["subtype", "count"]
            st.dataframe(subtype_counts, use_container_width=True, hide_index=True)
    if not st.session_state.change_log.empty:
        st.subheader("Recent Changes")
        st.dataframe(
            st.session_state.change_log.sort_values("timestamp", ascending=False).head(20),
            use_container_width=True,
            hide_index=True,
        )
    if not st.session_state.tap_records.empty:
        st.subheader("TAP Summary")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("TAP Records", len(st.session_state.tap_records))
        c2.metric("Unique TAPs", st.session_state.tap_records["tap"].nunique())
        c3.metric("Assigned Ports", int((st.session_state.tap_records["status"] == "assigned").sum()))
        if "project" in st.session_state.tap_records.columns:
            c4.metric("Projects", st.session_state.tap_records["project"].replace("", pd.NA).dropna().nunique())
        else:
            c4.metric("Projects", 0)
        st.dataframe(st.session_state.tap_records.head(25), use_container_width=True)
    else:
        st.info("Import your CO Fibers spreadsheet from the TAP / Customer Fiber Map page.")

elif page == "🗺️ TAP / Customer Fiber Map":
    st.header("TAP / Customer Fiber Map")
    st.caption("Import spreadsheet columns: Tap, PORT, Cable, Customer, CO Fiber, Pole, Street.")

    with st.container(border=True):
        st.subheader("Import TAP Project / Location")

        import_mode = st.radio(
            "Import into site",
            ["Existing Site", "Create New Site"],
            horizontal=True,
        )
        if import_mode == "Existing Site":
            selected_site_id = st.selectbox(
                "Existing Site *",
                st.session_state.sites["site_id"].tolist(),
                format_func=lambda sid: get_site_name(sid),
            )
            new_site_name = ""
            new_site_address = ""
        else:
            selected_site_id = None
            new_site_name = st.text_input("New Site Name *", placeholder="Example: Smyrna CO, Oakfield Build, Houlton South")
            new_site_address = st.text_input("New Site Address / Area", placeholder="Town, road, CO address, or service area")

        col_a, col_b = st.columns(2)
        with col_a:
            import_project = st.text_input(
                "Project / Location Name *",
                placeholder="Example: Smyrna Phase 1, Houlton CO, Oakfield Build",
            )
        with col_b:
            import_location = st.text_input(
                "Physical Location / Area",
                placeholder="Town, CO, node, or service area",
            )
        uploaded = st.file_uploader("Upload CO Fibers spreadsheet", type=["xlsx", "xls", "csv"])

    if uploaded:
        if uploaded.name.lower().endswith(".csv"):
            raw = pd.read_csv(uploaded)
        else:
            raw = pd.read_excel(uploaded)

        preview_site_name = get_site_name(selected_site_id) if import_mode == "Existing Site" and selected_site_id else new_site_name.strip()
        mapped = normalize_tap_import(raw, project=import_project.strip(), location=import_location.strip())
        mapped["site_id"] = selected_site_id if selected_site_id else "NEW"
        mapped["site_name"] = preview_site_name

        st.success(f"Loaded {len(mapped)} TAP records for site: {preview_site_name or 'Not set yet'} / project: {import_project or 'Not set yet'}.")
        st.dataframe(mapped, use_container_width=True)

        can_import = bool(import_project.strip()) and ((import_mode == "Existing Site" and selected_site_id is not None) or (import_mode == "Create New Site" and bool(new_site_name.strip())))
        if not import_project.strip():
            st.warning("Enter a Project / Location Name before importing so the cables and circuits are tied to the right project.")
        if import_mode == "Create New Site" and not new_site_name.strip():
            st.warning("Enter the New Site Name before importing.")

        if st.button("Import TAP records and create site cables/circuits", type="primary", disabled=not can_import):
            if import_mode == "Create New Site":
                target_site_id = create_site(new_site_name.strip(), new_site_address.strip())
            else:
                target_site_id = int(selected_site_id)
            target_site_name = get_site_name(target_site_id)
            mapped["site_id"] = target_site_id
            mapped["site_name"] = target_site_name

            existing = st.session_state.tap_records.copy()
            st.session_state.tap_records = (
                pd.concat([existing, mapped.copy()], ignore_index=True)
                if not existing.empty else mapped.copy()
            )
            added_cables, added_circuits = create_tap_circuits_from_records(mapped, site_id=target_site_id, site_name=target_site_name)
            st.success(
                f"Imported {len(mapped)} TAP rows into site {target_site_name} / project {import_project}. "
                f"Created {added_cables} cables and {added_circuits} customer/TAP circuits."
            )
            st.rerun()

    if not st.session_state.tap_records.empty:
        st.subheader("Search TAP Records")
        df = st.session_state.tap_records.copy()
        project_values = []
        if "project" in df.columns:
            project_values = sorted([x for x in df["project"].dropna().astype(str).unique().tolist() if x])
        selected_project = st.selectbox("Filter by project/location", ["All"] + project_values)
        q = st.text_input("Search customer, TAP, cable, CO fiber, pole, street, project, or location")
        if selected_project != "All":
            df = df[df["project"].astype(str) == selected_project]
        if q:
            mask = df.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)
            df = df[mask]
        st.dataframe(df, use_container_width=True)
        selected_circuit = st.selectbox("Open circuit from TAP map", [""] + df["circuit_id"].astype(str).tolist())
        if selected_circuit:
            show_circuit_path(selected_circuit)

elif page == "🧱 Rack & Equipment View":
    st.header("Rack & Equipment View")
    rack = st.selectbox("Rack", st.session_state.racks["rack_id"].tolist(), format_func=lambda rid: st.session_state.racks[st.session_state.racks["rack_id"] == rid].iloc[0]["name"])
    rack_devices = st.session_state.devices[st.session_state.devices["rack_id"] == rack].copy()
    selected_device = None
    if not rack_devices.empty:
        selected_device = st.selectbox("Equipment / Patch Panel", rack_devices["device_id"].tolist(), format_func=lambda did: rack_devices[rack_devices["device_id"] == did].iloc[0]["name"])
    circuit_options = [""] + st.session_state.circuits["circuit_id"].astype(str).tolist()
    selected_circuit = st.selectbox("Selected circuit to view/highlight", circuit_options)
    left, right = st.columns([1, 1])
    with left:
        rack_block_view(rack, selected_device_id=selected_device, selected_circuit_id=selected_circuit or None)
    with right:
        if selected_device:
            show_device_ports(selected_device)
            ids = circuit_ids_touching_device(selected_device)
            if ids:
                st.subheader("Circuits using this equipment")
                st.dataframe(st.session_state.circuits[st.session_state.circuits["circuit_id"].isin(ids)], use_container_width=True)
        if selected_circuit:
            show_circuit_path(selected_circuit)

elif page == "🔌 Build Cable / Circuit":
    st.header("Build Cable / Circuit")
    st.info("Track incoming cables, internal patch cables, and stitch them into end-to-end circuits.")
    tab_cable, tab_circuit = st.tabs(["Create Physical Cable Segment", "Create / Update Logical Circuit"])

    with tab_cable:
        used = used_port_ids()
        col1, col2 = st.columns(2)
        col1.write("**Quick pick A-End from rack view:** " + port_label(st.session_state.get("pending_a_port")))
        col2.write("**Quick pick Z-End from rack view:** " + port_label(st.session_state.get("pending_z_port")))
        with st.form("create_cable_segment"):
            c1, c2, c3 = st.columns(3)
            cable_id = c1.text_input("Cable ID *", value=f"CBL-{datetime.now().strftime('%Y%m%d%H%M')}")
            cable_type = c2.selectbox("Cable Type", ["fiber", "ethernet", "coax", "other"])
            subtype = c3.selectbox("Subtype", ["incoming", "cross_connect", "patch", "backbone", "tap_drop_or_distribution", "mapped_existing_cable"])
            project = st.text_input("Project / Location Name")
            c4, c5, c6 = st.columns(3)
            location = c4.text_input("Physical Area")
            strand = c5.text_input("Fiber / Pair / Strand")
            color = c6.text_input("Color", value="yellow" if cable_type == "fiber" else "blue")
            site_id = st.selectbox("Site", st.session_state.sites["site_id"].tolist(), format_func=lambda sid: get_site_name(sid))

            a_type, z_type = st.columns(2)
            a_end_type = a_type.radio("A-End Type", ["device_port", "external_handoff"], horizontal=True, key="a_end_type")
            z_end_type = z_type.radio("Z-End Type", ["device_port", "external_handoff"], horizontal=True, key="z_end_type")

            p1, p2 = st.columns(2)
            default_a = st.session_state.get("pending_a_port")
            default_z = st.session_state.get("pending_z_port")
            a_port = p1.selectbox(
                "A-End Device Port",
                [None] + st.session_state.ports["port_id"].astype(int).tolist(),
                index=([None] + st.session_state.ports["port_id"].astype(int).tolist()).index(default_a) if default_a in st.session_state.ports["port_id"].astype(int).tolist() else 0,
                format_func=lambda pid: "— select —" if pid is None else port_label(pid),
                disabled=a_end_type != "device_port",
            )
            z_port = p2.selectbox(
                "Z-End Device Port",
                [None] + st.session_state.ports["port_id"].astype(int).tolist(),
                index=([None] + st.session_state.ports["port_id"].astype(int).tolist()).index(default_z) if default_z in st.session_state.ports["port_id"].astype(int).tolist() else 0,
                format_func=lambda pid: "— select —" if pid is None else port_label(pid),
                disabled=z_end_type != "device_port",
            )
            a_desc = p1.text_input("A-End External Handoff Label", placeholder="MMR Demarc A / Carrier panel 1/1", disabled=a_end_type != "external_handoff")
            z_desc = p2.text_input("Z-End External Handoff Label", placeholder="OSP Vault / Building Entrance", disabled=z_end_type != "external_handoff")
            allow_reuse = st.checkbox("Allow a device port already in use", value=False)

            submit_cable = st.form_submit_button("Create Cable Segment", type="primary")
            if submit_cable:
                errors = []
                if not str(cable_id).strip():
                    errors.append("Cable ID is required.")
                if not st.session_state.cables[st.session_state.cables["cable_id"].astype(str) == str(cable_id)].empty:
                    errors.append("Cable ID already exists.")
                if a_end_type == "device_port" and a_port is None:
                    errors.append("Pick an A-End device port or switch A-End to external handoff.")
                if z_end_type == "device_port" and z_port is None:
                    errors.append("Pick a Z-End device port or switch Z-End to external handoff.")
                if a_end_type == "external_handoff" and not str(a_desc).strip():
                    errors.append("Enter A-End external handoff label.")
                if z_end_type == "external_handoff" and not str(z_desc).strip():
                    errors.append("Enter Z-End external handoff label.")
                if a_end_type == "device_port" and z_end_type == "device_port" and int(a_port) == int(z_port):
                    errors.append("A-End and Z-End cannot be the same port.")
                if not allow_reuse:
                    if a_end_type == "device_port" and int(a_port) in used:
                        errors.append("A-End port already has a cable. Enable 'Allow reuse' to override.")
                    if z_end_type == "device_port" and int(z_port) in used:
                        errors.append("Z-End port already has a cable. Enable 'Allow reuse' to override.")
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    row = pd.DataFrame([{
                        "cable_id": str(cable_id).strip(),
                        "cable_type": cable_type,
                        "color": color,
                        "fiber_count": 1 if cable_type == "fiber" else None,
                        "subtype": subtype,
                        "a_port_id": int(a_port) if a_end_type == "device_port" else None,
                        "z_port_id": int(z_port) if z_end_type == "device_port" else None,
                        "a_description": endpoint_label(a_end_type, a_port, a_desc),
                        "z_description": endpoint_label(z_end_type, z_port, z_desc),
                        "length": None,
                        "strand": strand,
                        "site_id": int(site_id),
                        "site_name": get_site_name(site_id),
                        "project": project.strip(),
                        "location": location.strip(),
                    }])
                    st.session_state.cables = pd.concat([st.session_state.cables, row], ignore_index=True)
                    log_event("create", "cable", cable_id, f"{subtype} {endpoint_label(a_end_type, a_port, a_desc)} -> {endpoint_label(z_end_type, z_port, z_desc)}")
                    st.success(f"Cable segment {cable_id} created.")
                    st.rerun()

    with tab_circuit:
        with st.form("create_or_update_circuit"):
            circuit_id = st.text_input("Circuit ID *", value=f"CKT-{datetime.now().strftime('%Y%m%d%H%M')}")
            customer = st.text_input("Customer / Account #")
            carrier = st.text_input("Carrier", value="Pioneer")
            ctype = st.selectbox("Circuit Type", ["Customer Fiber / TAP", "DIA", "Transit", "MPLS", "Wavelength", "Point-to-Point", "Cross-Connect"])
            bandwidth = st.text_input("Bandwidth")
            status = st.selectbox("Status", ["active", "assigned", "pending", "available", "decommissioned"])
            site_id = st.selectbox("Site ", st.session_state.sites["site_id"].tolist(), format_func=lambda sid: get_site_name(sid))
            project = st.text_input("Project / Location Name ")
            location = st.text_input("Physical Area ")
            cable_options = st.session_state.cables["cable_id"].astype(str).tolist()
            selected_cables = st.multiselect("Cable segments in path order", cable_options)
            notes = st.text_area("Notes")
            submit_circuit = st.form_submit_button("Create / Update Circuit", type="primary")
            if submit_circuit:
                if not str(circuit_id).strip():
                    st.error("Circuit ID is required.")
                elif not selected_cables:
                    st.error("Select at least one cable segment.")
                else:
                    first_cable = st.session_state.cables[st.session_state.cables["cable_id"].astype(str) == str(selected_cables[0])].iloc[0]
                    last_cable = st.session_state.cables[st.session_state.cables["cable_id"].astype(str) == str(selected_cables[-1])].iloc[0]
                    row = {
                        "circuit_id": str(circuit_id).strip(),
                        "carrier": carrier,
                        "circuit_type": ctype,
                        "bandwidth": bandwidth,
                        "status": status,
                        "a_end": str(first_cable.get("a_description", "")),
                        "z_end": str(last_cable.get("z_description", "")),
                        "cable_ids": selected_cables,
                        "notes": notes,
                        "customer": customer,
                        "tap": "",
                        "tap_port": "",
                        "co_fiber": "",
                        "street": "",
                        "pole": "",
                        "project": project.strip(),
                        "location": location.strip(),
                        "site_id": int(site_id),
                        "site_name": get_site_name(site_id),
                    }
                    exists = st.session_state.circuits["circuit_id"].astype(str) == str(circuit_id).strip()
                    if exists.any():
                        for k, v in row.items():
                            st.session_state.circuits.loc[exists, k] = [v]
                        log_event("update", "circuit", circuit_id, f"{len(selected_cables)} cable segments")
                        st.success(f"Circuit {circuit_id} updated.")
                    else:
                        st.session_state.circuits = pd.concat([st.session_state.circuits, pd.DataFrame([row])], ignore_index=True)
                        log_event("create", "circuit", circuit_id, f"{len(selected_cables)} cable segments")
                        st.success(f"Circuit {circuit_id} created.")
                    st.rerun()

elif page == "📋 Cables":
    st.header("Cables")
    df = st.session_state.cables.copy()
    subtype_values = sorted([x for x in df["subtype"].dropna().astype(str).unique().tolist()]) if not df.empty and "subtype" in df.columns else []
    selected_subtype = st.selectbox("Subtype", ["All"] + subtype_values)
    if selected_subtype != "All" and not df.empty:
        df = df[df["subtype"].astype(str) == selected_subtype]
    q = st.text_input("Search cables")
    if q and not df.empty:
        df = df[df.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)]
    if not df.empty:
        df["A-End"] = df.apply(lambda r: port_label(r["a_port_id"]) if pd.notna(r["a_port_id"]) else str(r.get("a_description", "")), axis=1)
        df["Z-End"] = df.apply(lambda r: port_label(r["z_port_id"]) if pd.notna(r["z_port_id"]) else str(r.get("z_description", "")), axis=1)
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    st.session_state.cables = edited.drop(columns=[c for c in ["A-End", "Z-End"] if c in edited.columns], errors="ignore")

elif page == "📡 Circuits":
    st.header("Circuits")
    df = st.session_state.circuits.copy()

    site_values = []
    if "site_name" in df.columns:
        site_values = sorted([x for x in df["site_name"].dropna().astype(str).unique().tolist() if x])
    selected_site = st.selectbox("Site", ["All"] + site_values)
    if selected_site != "All" and not df.empty:
        df = df[df["site_name"].astype(str) == selected_site]

    location_values = []
    if "project" in df.columns:
        location_values += [x for x in df["project"].dropna().astype(str).unique().tolist() if x]
    if "location" in df.columns:
        location_values += [x for x in df["location"].dropna().astype(str).unique().tolist() if x]
    location_values = sorted(set(location_values))
    selected_location = st.selectbox("Project / Location", ["All"] + location_values)
    if selected_location != "All" and not df.empty:
        project_match = df["project"].astype(str) == selected_location if "project" in df.columns else False
        location_match = df["location"].astype(str) == selected_location if "location" in df.columns else False
        df = df[project_match | location_match]

    q = st.text_input("Search circuits")
    if q and not df.empty:
        df = df[df.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)]
    st.dataframe(df, use_container_width=True)
    selected = st.selectbox("Open Circuit", [""] + df["circuit_id"].astype(str).tolist() if not df.empty else [""])
    if selected:
        show_circuit_path(selected)
        if st.button("Delete selected circuit", type="secondary"):
            st.session_state.circuits = st.session_state.circuits[st.session_state.circuits["circuit_id"] != selected].copy()
            log_event("delete", "circuit", selected, "Circuit removed from inventory")
            st.success("Circuit deleted.")
            st.rerun()

elif page == "⚙️ Manage Racks & Equipment":
    st.header("Manage Racks & Equipment")
    tab1, tab2 = st.tabs(["Racks", "Equipment / Patch Panels"])
    with tab1:
        st.dataframe(st.session_state.racks, use_container_width=True)
        with st.form("add_rack"):
            name = st.text_input("Rack Name")
            room = st.text_input("Room")
            u_height = st.number_input("U Height", min_value=1, max_value=52, value=42)
            if st.form_submit_button("Add Rack") and name:
                new_id = int(st.session_state.racks["rack_id"].max() + 1) if not st.session_state.racks.empty else 1
                st.session_state.racks = pd.concat([st.session_state.racks, pd.DataFrame([{"rack_id": new_id, "site_id": 1, "room": room, "name": name, "u_height": u_height}])], ignore_index=True)
                st.rerun()
        del_rack = st.selectbox("Delete Rack", [""] + st.session_state.racks["rack_id"].astype(str).tolist(), format_func=lambda x: "" if x == "" else st.session_state.racks[st.session_state.racks["rack_id"] == int(x)].iloc[0]["name"])
        if del_rack and st.button("Delete selected rack"):
            rid = int(del_rack)
            st.session_state.devices = st.session_state.devices[st.session_state.devices["rack_id"] != rid].copy()
            st.session_state.racks = st.session_state.racks[st.session_state.racks["rack_id"] != rid].copy()
            st.rerun()
    with tab2:
        st.dataframe(st.session_state.devices, use_container_width=True)
        with st.form("add_device"):
            rack_id = st.selectbox("Rack", st.session_state.racks["rack_id"].tolist(), format_func=lambda rid: st.session_state.racks[st.session_state.racks["rack_id"] == rid].iloc[0]["name"])
            name = st.text_input("Equipment Name")
            role = st.selectbox("Type", ["fiber_patch_panel", "ethernet_patch_panel", "network_device", "tap_terminal_access_port", "router", "switch"])
            position = st.number_input("Start U", min_value=1, max_value=52, value=1)
            u_height = st.number_input("U Height", min_value=1, max_value=20, value=1)
            port_count = st.number_input("Port Count", min_value=0, max_value=864, value=24)
            port_prefix = st.text_input("Port Prefix", value="LC" if "fiber" in role else "P")
            if st.form_submit_button("Add Equipment") and name:
                new_id = int(st.session_state.devices["device_id"].max() + 1) if not st.session_state.devices.empty else 1
                st.session_state.devices = pd.concat([st.session_state.devices, pd.DataFrame([{
                    "device_id": new_id, "rack_id": rack_id, "name": name, "role": role, "position": position,
                    "u_height": u_height, "port_count": port_count, "port_prefix": port_prefix,
                }])], ignore_index=True)
                ensure_ports_for_device(new_id)
                st.rerun()
        edit_id = st.selectbox("Edit / Delete Equipment", [""] + st.session_state.devices["device_id"].astype(str).tolist(), format_func=lambda x: "" if x == "" else st.session_state.devices[st.session_state.devices["device_id"] == int(x)].iloc[0]["name"])
        if edit_id:
            did = int(edit_id)
            row = st.session_state.devices[st.session_state.devices["device_id"] == did].iloc[0]
            with st.form("edit_device"):
                name = st.text_input("Name", value=row["name"])
                position = st.number_input("Start U", min_value=1, max_value=52, value=int(row["position"]))
                u_height = st.number_input("U Height", min_value=1, max_value=20, value=int(row["u_height"]))
                port_count = st.number_input("Port Count", min_value=0, max_value=864, value=int(row.get("port_count", 0) or 0))
                save = st.form_submit_button("Save Equipment")
                if save:
                    mask = st.session_state.devices["device_id"] == did
                    st.session_state.devices.loc[mask, "name"] = name
                    st.session_state.devices.loc[mask, "position"] = position
                    st.session_state.devices.loc[mask, "u_height"] = u_height
                    st.session_state.devices.loc[mask, "port_count"] = port_count
                    ensure_ports_for_device(did)
                    st.rerun()
            if st.button("Delete Equipment"):
                ports = st.session_state.ports[st.session_state.ports["device_id"] == did]["port_id"].tolist()
                st.session_state.cables = st.session_state.cables[~(st.session_state.cables["a_port_id"].isin(ports) | st.session_state.cables["z_port_id"].isin(ports))].copy()
                st.session_state.ports = st.session_state.ports[st.session_state.ports["device_id"] != did].copy()
                st.session_state.devices = st.session_state.devices[st.session_state.devices["device_id"] != did].copy()
                st.rerun()

st.sidebar.caption("TAP import supports Project/Location + Tap, Port, Cable, Customer, CO Fiber, Pole, Street.")
