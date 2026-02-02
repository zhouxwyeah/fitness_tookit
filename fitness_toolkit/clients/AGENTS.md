# clients/ - Platform API Clients

> API integrations for fitness platforms (Garmin China, COROS)

---

## OVERVIEW

All clients extend `BaseClient` ABC. Each platform has one client class handling auth + activity operations.

---

## STRUCTURE

| File | Class | API | Auth Method |
|------|-------|-----|-------------|
| base.py | `BaseClient` | ABC | N/A |
| garmin.py | `GarminClient` | Garmin China | `Client.login()` |
| coros.py | `CorosClient` | COROS Training Hub | MD5 password + accessToken |

---

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Add new platform | Create `newplatform.py`, extend `BaseClient` |
| Fix Garmin auth | `garmin.py` → `login()`, check garth config |
| Fix COROS auth | `coros.py` → `login()`, check MD5 hash |
| Modify download format | `download_activity()` in respective client |
| Handle upload errors | `garmin.py` → `upload_fit()` error handling |

---

## INTERFACE (BaseClient)

```python
class BaseClient(ABC):
    authenticated: bool
    token: Optional[str]

    @abstractmethod
    def login(self, email: str, password: str) -> bool:
        ...

    @abstractmethod
    def get_activities(
        self,
        start_date: date,
        end_date: date,
        activity_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def download_activity(self, activity_id: str, format: str, save_path: Path) -> Optional[Path]:
        ...


class GarminClient(BaseClient):
    def upload_fit(
        self,
        file_path: Path,
        activity_name: Optional[str] = None,
        start_time: Any = None,
    ) -> Optional[str]:
        ...
```

---

## GARMIN CLIENT PATTERNS

### garth Library Usage
```python
from garth import Client

# Login
client = Client(domain="garmin.cn")
client.login(email, password)

# API calls
client.connectapi("/activitylist-service/activities/search/activities", params={...})

# File download
client.download("/download-service/export/fit/activity/{id}")

# File upload (China requires nk header)
client.post("connectapi", "/upload-service/upload", api=True, files=files, headers={"nk": "NT"})
```

### Upload Response Handling
```python
result = response.json()
detailed = result.get("detailedImportResult", result)

# Success
if detailed.get("successes"):
    activity_id = detailed["successes"][0]["internalId"]

# Duplicate (code 202 or 409 HTTP)
if messages[0].get("code") == 202:
    return "duplicate"
```

---

## COROS CLIENT PATTERNS

### Auth Flow
```python
# Password hashing (COROS uses MD5)
pwd_hash = hashlib.md5(password.encode()).hexdigest()

# Login endpoint
POST /account/login
{"account": email, "accountType": 2, "pwd": pwd_hash}

# Response: accessToken → set in session headers
self.session.headers["accesstoken"] = token
```

### Activity Download
```python
# Step 1: Get file URL
POST /activity/detail/download
params: labelId, sportType, fileType (1=gpx, 3=tcx, 4=fit)

# Step 2: Download from returned fileUrl
GET {fileUrl}
```

### File Type Constants
```python
COROS_FILE_TYPES = {
    "gpx": 1,
    "fit": 4,
    "tcx": 3,  # TCX has extension compatibility issues with Garmin
}
```

---

## ANTI-PATTERNS

| Pattern | Why | Instead |
|---------|-----|---------|
| Use TCX for transfer | COROS TCX extensions incompatible with Garmin | Use FIT format |
| Ignore 409 errors | Duplicate activity is normal | Return "duplicate", mark as skipped |
| Skip rate limiting | API throttling | `time.sleep(Config.RATE_LIMIT_DELAY)` |
| Log tokens | Security | Never log auth data |

---

## GOTCHAS

1. **Garmin China domain**: Use `Client(domain="garmin.cn")` for all operations
2. **COROS date format**: Uses `YYYYMMDD` not ISO format (`startDay`, `endDay`)
3. **garth.client.post** for uploads: Use `api=True` + `headers={"nk": "NT"}` for China endpoint
4. **COROS activity ID**: Called `labelId` in API, paired with `sportType` for downloads
5. **Empty upload result**: Garmin sometimes returns empty successes/failures; confirm duplicates by searching for an existing activity near the start time
