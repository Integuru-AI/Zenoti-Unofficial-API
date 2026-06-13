import json
import requests
import concurrent.futures
from urllib.parse import urlencode

# API base URL is different from web app URL
API_BASE_URL = "https://<API-SUBDOMAIN>.zenoti.com"


def run(headers, user_input):
    """
    Fetch comprehensive guest profile data from Zenoti.

    Retrieves all guest data including: profile, notes, appointments, products,
    memberships, packages, prepaid cards, gift cards, wallet, issues, notifications,
    payments, invoices, forms, gallery, coupons, loyalty points, and credits.
    """
    guest_id = user_input.get("guest_id")
    if not guest_id:
        return {"status_code": 400, "body": {"error": "guest_id is required"}}

    center_id = user_input.get("center_id")
    if not center_id:
        return {"status_code": 400, "body": {"error": "center_id is required"}}

    # Prepare API headers
    api_headers = {
        "Authorization": headers.get("authorization") or headers.get("Authorization"),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-languagecode": "en-US",
        "Cache-Control": "no-cache"
    }

    if not api_headers["Authorization"]:
        return {"status_code": 400, "body": {"error": "Authorization header with Bearer token is required"}}

    try:
        results, session_expired = _fetch_all_data(guest_id, center_id, api_headers)
    except Exception as e:
        return {"status_code": 500, "body": {"error": str(e)}}

    # If any endpoint returned 401, return session expired
    if session_expired:
        return {"status_code": 401, "body": {"error": "Session expired, please refresh authentication"}}

    # Organize results into a clean structure
    output = {
        "guest_id": guest_id,
        "center_id": center_id,
        "profile": results.get("profile"),
        "indicators": results.get("indicators"),
        "metrics": results.get("metrics"),
        "notes": results.get("notes"),
        "medical_notes": results.get("medical_notes"),
        "appointments": {
            "upcoming": results.get("appointments_upcoming"),
            "past": results.get("appointments_past")
        },
        "products": results.get("products"),
        "memberships": results.get("memberships"),
        "packages": results.get("packages"),
        "prepaid_cards": results.get("prepaid_cards"),
        "gift_cards": {
            "active": results.get("gift_cards_active"),
            "redeemed": results.get("gift_cards_redeemed")
        },
        "wallet": results.get("wallet"),
        "issues": results.get("issues"),
        "notifications": results.get("notifications"),
        "payments": results.get("payments"),
        "open_invoices": results.get("open_invoices"),
        "forms": results.get("forms"),
        "gallery": results.get("gallery"),
        "images": results.get("images"),
        "coupons": results.get("coupons"),
        "loyalty_points": results.get("loyalty_points"),
        "credits": {
            "received": results.get("credits_received"),
            "used": results.get("credits_used")
        },
        "tags": results.get("tags")
    }

    return {"status_code": 200, "body": output}

# === PRIVATE ===

def _make_request(api_headers, endpoint, params=None):
    """Make a GET request to the API."""
    url = f"{API_BASE_URL}{endpoint}"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"

    try:
        response = requests.get(
            url,
            headers=api_headers,
            timeout=30
        )

        # Check for auth redirect (session expired)
        if response.status_code == 302 or "login" in response.url.lower():
            return {"error": "session_expired", "status": 401}

        if response.status_code == 401:
            return {"error": "unauthorized", "status": 401}

        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "status": response.status_code}

        return response.json()
    except Exception as e:
        return {"error": str(e)}


def _make_gallery_request(api_headers, guest_id, params=None):
    """Make a POST request for gallery/files (requires POST with filter body)."""
    url = f"{API_BASE_URL}/v1/guests/{guest_id}/files/filter"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"

    try:
        # POST with empty filter to get all files
        response = requests.post(
            url,
            headers=api_headers,
            json={"services": [], "tags": [], "date_range": None},
            timeout=30
        )

        if response.status_code == 401:
            return {"error": "unauthorized", "status": 401}

        if response.status_code != 200:
            # Gallery endpoint may return error if no services configured
            return {"results": [], "note": "Gallery requires service filters"}

        return response.json()
    except Exception as e:
        return {"error": str(e)}


def _fetch_all_data(guest_id, center_id, api_headers):
    """Fetch all guest profile data in parallel."""
    # Define all API endpoints to fetch
    endpoints = {
        # Guest Profile (basic info with all expansions)
        "profile": (f"/v1/guests/{guest_id}", {
            "expand": ["tags", "preferences", "address_info", "referral",
                      "primary_employee", "additional_details", "email_details", "blocked_therapists"]
        }),

        # Guest Indicators
        "indicators": (f"/v1/guests/{guest_id}/indicators", {"expand": "additional_info"}),

        # Guest Metrics
        "metrics": (f"/v1/guests/{guest_id}/metrics", {"monthly_filter": 1}),

        # Notes
        "notes": (f"/v1/guests/{guest_id}/notes", {
            "guest_id": guest_id,
            "view_private": "true",
            "page": 1,
            "size": 100,
            "privacy_type": [2, 3]
        }),

        # Medical Notes
        "medical_notes": (f"/v1/guests/{guest_id}/notes", {"noteType": 10}),

        # Upcoming Appointments
        "appointments_upcoming": (f"/v1/guests/{guest_id}/appointments/0", {
            "status": 5,
            "page": 1,
            "size": 100,
            "maskGC": "false"
        }),

        # Past Appointments
        "appointments_past": (f"/v1/guests/{guest_id}/appointments/1", {
            "status": 0,
            "page": 1,
            "size": 100,
            "maskGC": "false"
        }),

        # Products
        "products": (f"/v1/guests/{guest_id}/products", {"page": 1, "size": 100}),

        # Memberships
        "memberships": (f"/v1/guests/{guest_id}/Memberships", {
            "expand[0]": "show_only_guest_membership_details",
            "center_id": center_id,
            "show_redeemable": "true"
        }),

        # Packages (all statuses)
        "packages": (f"/v1/guests/{guest_id}/Packages", {
            "center_id": center_id,
            "show_redeemable": "true",
            "page_num": 1,
            "page_size": 100,
            "status": -1,
            "expand": "day_package_details"
        }),

        # Prepaid Cards
        "prepaid_cards": (f"/v1/guests/{guest_id}/prepaidcards", {
            "page": 1,
            "size": 100,
            "maskGC": "false"
        }),

        # Gift Cards (active)
        "gift_cards_active": (f"/v1/guests/{guest_id}/gift_cards", {
            "page": 1,
            "size": 100,
            "filter_by": 1,
            "expand": "benefits",
            "maskGC": "false"
        }),

        # Gift Cards (redeemed)
        "gift_cards_redeemed": (f"/v1/guests/{guest_id}/gift_cards", {
            "page": 1,
            "size": 100,
            "filter_by": 2,
            "expand": "benefits",
            "maskGC": "false"
        }),

        # Wallet/Accounts
        "wallet": (f"/v1/guests/{guest_id}/accounts", {
            "center_id": center_id,
            "source": 0,
            "accounts_from": 31,
            "get_shared_cards": "true",
            "get_expired_cards": "true",
            "get_address": "true",
            "get_avs_status": "true",
            "get_all_cards": "true"
        }),

        # Issues
        "issues": (f"/api/guests/{guest_id}/IssuesAndNotifications", {
            "PageSize": 100,
            "PageNum": 1,
            "Option": 0
        }),

        # Notifications
        "notifications": (f"/api/guests/{guest_id}/IssuesAndNotifications", {
            "PageSize": 100,
            "PageNum": 1,
            "Option": 1
        }),

        # Payments
        "payments": (f"/v1/guests/{guest_id}/payments", {
            "SearchType": 0,
            "TrasactionType": 0,
            "page": 1,
            "size": 100,
            "maskGC": "false"
        }),

        # Open Invoices
        "open_invoices": (f"/v1/guests/{guest_id}/open_invoices", {
            "page": 1,
            "size": 100,
            "sort_by": 2,
            "center_id": center_id,
            "mask_gc_number": "false"
        }),

        # Forms History
        "forms": (f"/api/Organizations/{guest_id}/GetFormsHistoryForGuest", None),

        # Profile Images
        "images": ("/v1/assets", {
            "pool_id": "UserImage",
            "object_id": guest_id,
            "filter_by": 1
        }),

        # Coupons
        "coupons": (f"/v1/guests/{guest_id}/coupons", {"page": 1, "size": 100}),

        # Loyalty Points
        "loyalty_points": (f"/v1/guests/{guest_id}/points", {
            "guestId": guest_id,
            "view_grooming_points": 1,
            "page_num": 1,
            "num_records": 100,
            "expand": ["get_points_history", "increment_value"]
        }),

        # Received Credits
        "credits_received": (f"/v1/guests/{guest_id}/received_credits", {"page": 1, "size": 100}),

        # Used Credits
        "credits_used": (f"/v1/guests/{guest_id}/used_credits", {"iPage": 1, "iRows": 100, "sort": "false"}),

        # Tags
        "tags": ("/v1/tags", {"item_type": 7, "item_id": guest_id, "page": -1, "size": -1}),
    }

    # Fetch all data in parallel
    results = {}
    session_expired = False

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_key = {
            executor.submit(_make_request, api_headers, endpoint, params): key
            for key, (endpoint, params) in endpoints.items()
        }

        for future in concurrent.futures.as_completed(future_to_key):
            key = future_to_key[future]
            try:
                data = future.result()
                results[key] = data

                # Check for session expiry
                if isinstance(data, dict) and data.get("status") == 401:
                    session_expired = True
            except Exception as e:
                results[key] = {"error": str(e)}

    # Fetch gallery separately (requires POST)
    results["gallery"] = _make_gallery_request(
        api_headers,
        guest_id,
        {"expand": ["services_info", "tags_info", "guidelines_info"], "page": 1, "size": 100}
    )

    return results, session_expired
