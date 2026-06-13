from curl_cffi import requests
import json
from datetime import datetime, timedelta

# Runtime-injected URLs (with fallbacks for testing)
try:
    _BASE_URL = BASE_URL
except NameError:
    _BASE_URL = "https://<API-SUBDOMAIN>.zenoti.com"

try:
    _APP_URL = APP_URL
except NameError:
    _APP_URL = "https://<SUBDOMAIN>.zenoti.com"


def run(headers, user_input):
    """
    List appointments for a date range with details including invoice items and forms.

    Returns appointments with: ID, patient info, dates/times, staff, status, room, service,
    invoice details (items, amounts), and associated forms.
    """
    app_url = _APP_URL

    # Parse and validate inputs
    start_date_str = user_input.get("start_date")
    end_date_str = user_input.get("end_date")
    center_id = user_input.get("center_id")
    org_id = user_input.get("org_id")
    if not center_id:
        return {'status_code': 400, 'body': {'error': 'center_id is required'}}
    if not org_id:
        return {'status_code': 400, 'body': {'error': 'org_id is required'}}
    include_cancelled = user_input.get("include_cancelled", False)
    include_invoice_details = user_input.get("include_invoice_details", True)

    if not start_date_str:
        return {'status_code': 400, 'body': {'error': 'start_date is required (format: YYYY-MM-DD)'}}
    if not end_date_str:
        return {'status_code': 400, 'body': {'error': 'end_date is required (format: YYYY-MM-DD)'}}

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    except ValueError:
        return {'status_code': 400, 'body': {'error': 'Invalid date format. Use YYYY-MM-DD'}}

    if end_date < start_date:
        return {'status_code': 400, 'body': {'error': 'end_date must be >= start_date'}}

    # Limit date range to prevent excessive API calls
    date_diff = (end_date - start_date).days
    if date_diff > 31:
        return {'status_code': 400, 'body': {'error': 'Date range cannot exceed 31 days'}}

    # Status code mapping
    STATUS_MAP = {
        "-2": "Cancelled",
        "-1": "No Show",
        "0": "New",
        "1": "Confirmed",
        "2": "Checked In",
        "3": "Started",
        "4": "Completed"
    }

    # Request headers for ASP.NET WebMethods
    request_headers = {
        "Cookie": headers.get("Cookie", ""),
        "Content-Type": "application/json; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Origin": app_url,
        "Referer": f"{app_url}/Appointment/ApptExtV2.aspx"
    }

    all_appointments = []
    all_forms = []

    # Iterate through each day in the range
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d") + " 00:00:00"

        payload = {
            "strAppDate": date_str,
            "orgId": org_id,
            "strCenterId": center_id,
            "strShowAllTherapist": "True",
            "mode": 0,
            "includenoshowcancelled": 1 if include_cancelled else 0,
            "includeVirtualAppts": -1,
            "isAmenities": False
        }

        try:
            response = requests.post(
                f"{app_url}/Appointment/ApptExtV2.aspx/GetInitialData",
                json=payload,
                headers=request_headers,
                impersonate="chrome131",
                timeout=30
            )
        except Exception as e:
            return {'status_code': 500, 'body': {'error': f'Request failed: {str(e)}'}}

        # Check for auth failure (redirect to login or 401)
        if response.status_code == 401:
            return {'status_code': 401, 'body': {'error': 'Session expired'}}

        if response.status_code == 302 or "login" in response.url.lower():
            return {'status_code': 401, 'body': {'error': 'Session expired - redirected to login'}}

        if response.status_code != 200:
            return {'status_code': response.status_code, 'body': {'error': f'API error: {response.text[:500]}'}}

        # Check for HTML login page in response
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type:
            if "login" in response.text.lower() or "sign in" in response.text.lower():
                return {'status_code': 401, 'body': {'error': 'Session expired - received login page'}}

        # Parse the triple-nested JSON response
        try:
            outer = response.json()
            d_string = outer.get("d", "")
            if not d_string:
                current_date += timedelta(days=1)
                continue

            data = json.loads(d_string)
            appts_str = data.get("Appts", "")
            if appts_str:
                appts_data = json.loads(appts_str)
                appointments = appts_data.get("appointments", [])
                forms = appts_data.get("apptForms", [])
                all_forms.extend(forms)

                for appt in appointments:
                    all_appointments.append(appt)
        except (json.JSONDecodeError, KeyError) as e:
            return {'status_code': 500, 'body': {'error': f'Failed to parse response: {str(e)}'}}

        current_date += timedelta(days=1)

    # Build forms lookup by appointment ID
    forms_by_appt = {}
    for form in all_forms:
        appt_id = form.get("appointmentId", "")
        if appt_id:
            if appt_id not in forms_by_appt:
                forms_by_appt[appt_id] = []
            forms_by_appt[appt_id].append({
                "form_id": form.get("formId", ""),
                "form_name": form.get("formName", ""),
                "is_filled": form.get("isFilled", "False") == "True"
            })

    # Process appointments and optionally fetch invoice details
    results = []
    invoice_cache = {}  # Cache invoice details to avoid duplicate calls

    for appt in all_appointments:
        # Skip cancelled if not requested
        status_code = str(appt.get("statustype", "0"))
        if not include_cancelled and status_code in ["-2", "-1"]:
            continue

        # Parse start/end times (format: "HH:MM MM-DD-YYYY")
        start_time_raw = appt.get("starttime", "")
        end_time_raw = appt.get("endtime", "")

        appt_date = ""
        start_time = ""
        end_time = ""

        if start_time_raw:
            parts = start_time_raw.split(" ")
            if len(parts) >= 2:
                start_time = parts[0]  # HH:MM
                date_parts = parts[1].split("-")  # MM-DD-YYYY
                if len(date_parts) == 3:
                    appt_date = f"{date_parts[2]}-{date_parts[0]}-{date_parts[1]}"  # YYYY-MM-DD

        if end_time_raw:
            parts = end_time_raw.split(" ")
            if len(parts) >= 1:
                end_time = parts[0]

        appointment_id = appt.get("appointmentid", "")
        invoice_id = appt.get("invoiceid", "")

        # Build base appointment object
        appointment_obj = {
            "appointment_id": appointment_id,
            "group_id": appt.get("groupid", ""),
            "patient_id": appt.get("userid", ""),
            "patient_name": appt.get("Name", ""),
            "patient_code": appt.get("UserCode", ""),
            "patient_email": appt.get("UserEmail", ""),
            "patient_phone": appt.get("mobilephone", ""),
            "date": appt_date,
            "start_time": start_time,
            "end_time": end_time,
            "duration_minutes": int(appt.get("servicelength", 0) or 0),
            "staff_id": appt.get("therapistid", ""),
            "staff_name": appt.get("therapistname", ""),
            "status": STATUS_MAP.get(status_code, f"Unknown ({status_code})"),
            "status_code": status_code,
            "room_id": appt.get("roomid", "") or None,
            "room_name": appt.get("room", "") or None,
            "service_id": appt.get("serviceid", ""),
            "service_name": appt.get("servicename", ""),
            "price": float(appt.get("price", 0) or 0),
            "notes": appt.get("note", ""),
            "created_by": appt.get("createdBy", ""),
            "invoice": None,
            "forms": forms_by_appt.get(appointment_id, [])
        }

        # Fetch invoice details if requested and invoice exists
        if include_invoice_details and invoice_id and invoice_id not in ["", "00000000-0000-0000-0000-000000000000"]:
            if invoice_id in invoice_cache:
                appointment_obj["invoice"] = invoice_cache[invoice_id]
            else:
                invoice_data = _fetch_invoice_details(app_url, request_headers, invoice_id)
                if invoice_data:
                    invoice_cache[invoice_id] = invoice_data
                    appointment_obj["invoice"] = invoice_data

        results.append(appointment_obj)

    return {
        'status_code': 200,
        'body': {
            'appointments': results,
            'count': len(results),
            'date_range': {
                'start': start_date_str,
                'end': end_date_str
            }
        }
    }


# === PRIVATE ===

def _fetch_invoice_details(app_url, headers, invoice_id):
    """Fetch invoice details including line items."""
    payload = {"strInvId": invoice_id}

    try:
        response = requests.post(
            f"{app_url}/Appointment/InvServices.aspx/GetInvDetails",
            json=payload,
            headers=headers,
            impersonate="chrome131",
            timeout=15
        )

        if response.status_code != 200:
            return None

        outer = response.json()
        d_string = outer.get("d", "")
        if not d_string:
            return None

        # Response format: items##$##date##$##tip##$##metadata##$##...

        items = []
        metadata = {}
        invoice_date = ""

        if "##$##" in d_string:
            parts = d_string.split("##$##")

            # Parse invoice items (index 0 - jqGrid format)
            try:
                items_json = _fix_json_escapes(parts[0])
                items_data = json.loads(items_json)
                items = _parse_invoice_items(items_data)
            except (json.JSONDecodeError, IndexError, ValueError):
                pass

            # Parse metadata (index 3)
            try:
                if len(parts) > 3 and parts[3].strip():
                    metadata_json = _fix_json_escapes(parts[3])
                    metadata = json.loads(metadata_json)
            except (json.JSONDecodeError, IndexError, ValueError):
                pass

            invoice_date = parts[1] if len(parts) > 1 else ""
        else:
            # Simple jqGrid format
            try:
                items_json = _fix_json_escapes(d_string)
                items_data = json.loads(items_json)
                items = _parse_invoice_items(items_data)
            except (json.JSONDecodeError, IndexError, ValueError):
                pass

        return {
            "invoice_id": invoice_id,
            "receipt_no": metadata.get("RcptNo", ""),
            "invoice_date": invoice_date,
            "status": "closed" if metadata.get("InvStatus") == "1" else "open",
            "center_id": metadata.get("CenterId", ""),
            "items": items,
            "tip_amount": _safe_float(metadata.get("TipAmount", "0")),
            "change": _safe_float(metadata.get("Change", "0"))
        }
    except Exception:
        return None


def _fix_json_escapes(s):
    """Fix invalid escape sequences in ASP.NET JSON responses."""
    import re
    # Replace invalid escape sequences like \> \< with just > <
    # These appear in HTML-formatted content within JSON strings
    s = re.sub(r'\\([^"\\/bfnrtu])', r'\1', s)
    return s


def _parse_invoice_items(items_data):
    """Parse invoice items from jqGrid data."""
    items = []
    for row in items_data.get("rows", []):
        cell = row.get("cell", [])
        if len(cell) > 17:
            item_name = _clean_item_name(cell[4] if len(cell) > 4 else "")
            # Skip empty item names
            if not item_name:
                continue
            items.append({
                "item_name": item_name,
                "item_type": cell[5] if len(cell) > 5 else "",
                "quantity": _safe_float(cell[8] if len(cell) > 8 else "1"),
                "price": _safe_float(cell[9] if len(cell) > 9 else "0"),
                "discount": _safe_float(cell[12] if len(cell) > 12 else "0"),
                "tax": _safe_float(cell[13] if len(cell) > 13 else "0"),
                "final_price": _safe_float(cell[15] if len(cell) > 15 else "0"),
                "therapist": cell[17] if len(cell) > 17 else "",
                "item_code": cell[36] if len(cell) > 36 else ""
            })
    return items


def _clean_item_name(name):
    """Remove HTML/markup from item name."""
    if not name:
        return ""
    # Remove common markup patterns
    import re
    name = re.sub(r'<[^>]+>', '', name)
    name = re.sub(r'\$#\$[^$]*\$#\$', '', name)
    return name.strip()


def _safe_float(value):
    """Safely convert to float."""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Remove currency symbols and commas
            cleaned = value.replace('$', '').replace(',', '').strip()
            return float(cleaned) if cleaned else 0.0
        return 0.0
    except (ValueError, TypeError):
        return 0.0
