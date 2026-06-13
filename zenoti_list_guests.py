import re
from curl_cffi import requests


def run(headers, user_input):
    """List all guests from Zenoti with pagination support."""
    base_url = APP_URL

    # Get optional parameters
    center_id = user_input.get("center_id")
    page = user_input.get("page", 1)
    size = user_input.get("size", 100)

    try:
        token_info = _extract_token_and_api_url(base_url, headers)
    except SessionExpiredError as e:
        return {'status_code': 401, 'body': {'error': str(e)}}
    except ExtractionError as e:
        return {'status_code': 500, 'body': {'error': str(e)}}

    api_token = token_info["api_token"]
    api_url = token_info["api_url"]

    # If center_id not provided, use default from page
    if not center_id:
        center_id = token_info.get("center_id")
        if not center_id:
            return {'status_code': 400, 'body': {'error': 'center_id is required and could not be auto-detected'}}

    try:
        result = _call_api(api_url, api_token, center_id, page, size)
    except AuthError:
        return {'status_code': 401, 'body': {'error': 'API authentication failed'}}
    except ApiError as e:
        return {'status_code': e.status_code, 'body': {'error': str(e)}}
    except Exception as e:
        return {'status_code': 500, 'body': {'error': str(e)}}

    return {
        'status_code': 200,
        'body': {
            'guests': result.get('guests', []),
            'page_info': result.get('page_Info', {})
        }
    }

# === PRIVATE ===


class SessionExpiredError(Exception):
    pass


class ExtractionError(Exception):
    pass


class AuthError(Exception):
    pass


class ApiError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        super().__init__(message)


def _extract_token_and_api_url(base_url, headers):
    """Fetch an authenticated page and extract API token, URL, and center ID."""
    page_response = requests.get(
        f"{base_url}/Guests/Guest.aspx",
        headers={"Cookie": headers.get("Cookie", "")},
        impersonate="chrome131",
        timeout=30
    )

    # Check for session expiry (redirected to login)
    if "login" in page_response.url.lower() or "/ids/" in page_response.url.lower():
        raise SessionExpiredError("Session expired")

    html = page_response.text

    # Extract API token
    token_match = re.search(r"globalWebApiToken\s*=\s*['\"]([^'\"]+)['\"]", html)
    if not token_match:
        raise SessionExpiredError("Could not extract API token - session may be expired")

    # Extract API URL
    api_url_match = re.search(r"globalWebApiUrl\s*=\s*['\"]([^'\"]+)['\"]", html)
    if not api_url_match:
        raise ExtractionError("Could not extract API URL")

    # Extract default center ID
    center_id = None
    center_match = re.search(r"globalCenterId\s*=\s*['\"]([^'\"]+)['\"]", html)
    if center_match:
        center_id = center_match.group(1)

    return {
        "api_token": token_match.group(1),
        "api_url": api_url_match.group(1),
        "center_id": center_id
    }


def _call_api(api_url, api_token, center_id, page, size):
    """Call the Zenoti REST API to list guests."""
    api_headers = {
        "Authorization": f"bearer {api_token}",
        "application_name": "web",
        "Content-Type": "application/json"
    }

    params = {
        "center_id": center_id,
        "page": page,
        "size": size
    }

    api_response = requests.get(
        f"{api_url}v1/guests",
        headers=api_headers,
        params=params,
        impersonate="chrome131",
        timeout=30
    )

    if api_response.status_code == 401:
        raise AuthError("API authentication failed")

    if api_response.status_code != 200:
        raise ApiError(api_response.status_code, f"API error: {api_response.text}")

    return api_response.json()
