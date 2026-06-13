from curl_cffi import requests
import json


def run(headers, user_input):
    """List employees with optional filtering and pagination."""
    # Extract and validate inputs
    center_id = user_input.get("center_id", "")
    status = user_input.get("status", "active").lower()
    page_size = user_input.get("page_size", 100)
    page = user_input.get("page", 1)
    search_text = user_input.get("search_text", "")
    sort_by = user_input.get("sort_by", "first_name").lower()
    sort_ascending = user_input.get("sort_ascending", True)
    job_ids = user_input.get("job_ids", [])

    # Map status to API values
    status_map = {
        "active": "0",
        "inactive": "1",
        "all": "2"
    }
    api_status = status_map.get(status, "0")

    # Map sort_by to API column names
    sort_col_map = {
        "code": "EmployeeCode",
        "first_name": "FirstName",
        "last_name": "LastName",
        "center": "CenterName",
        "phone": "MobilePhone",
        "job": "EmployeeTypeName",
        "status": "STATUS"
    }
    api_sort_col = sort_col_map.get(sort_by, "FirstName")

    # Build the request payload
    payload = {
        "inputParam": {
            "iCommissionSettingsViewOnlySelfPerm": 0,
            "strViewId": center_id,
            "iViewMode": 2 if center_id else 0,
            "iPageSize": page_size,
            "iPageNum": page,
            "sortCol": api_sort_col,
            "sortOrder": sort_ascending,
            "searchText": search_text,
            "status": api_status,
            "jobs": job_ids,
            "CenterIds": []
        }
    }

    try:
        result = _call_api(payload, headers)
    except Exception as e:
        return {'status_code': 500, 'body': {'error': str(e)}}

    if result.get("session_expired"):
        return {'status_code': 401, 'body': {'error': 'Session expired'}}

    data = result.get("data")
    if data is None:
        return {'status_code': 200, 'body': result.get("raw", {})}

    # Extract and normalize employee data
    employees = []
    for emp in data.get("rowData", []):
        employees.append({
            "employee_id": emp.get("EmployeeId"),
            "code": emp.get("EmployeeCode"),
            "first_name": emp.get("FirstName"),
            "last_name": emp.get("LastName"),
            "nickname": emp.get("NickName"),
            "phone": emp.get("MobilePhone"),
            "phone_country_code": emp.get("MobileCountryCode"),
            "job_type": emp.get("EmployeeTypeName"),
            "status": emp.get("STATUS"),
            "center_name": emp.get("CenterName"),
            "is_consultant": emp.get("IsConsultant"),
            "is_online_booking_enabled": emp.get("IsOnlineBookingEnabled")
        })

    return {
        'status_code': 200,
        'body': {
            'employees': employees,
            'total_count': data.get("lastRow", len(employees))
        }
    }

# === PRIVATE ===

def _call_api(payload, headers):
    """Make the API request to fetch employee grid data."""
    base_url = APP_URL

    response = requests.post(
        f"{base_url}/ListingPages/EmployeeDetailsV2.aspx/GetGridData",
        json=payload,
        headers={
            **headers,
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01"
        },
        impersonate="chrome131",
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(f"API returned status {response.status_code}: {response.text}")

    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        return {"session_expired": True}

    try:
        result = response.json()
    except json.JSONDecodeError:
        return {"session_expired": True}

    # ASP.NET WebMethod wraps response in {"d": "<json_string>"}
    if "d" in result:
        try:
            data = json.loads(result["d"])
        except (json.JSONDecodeError, TypeError):
            data = result["d"]
        return {"data": data}

    return {"raw": result}
