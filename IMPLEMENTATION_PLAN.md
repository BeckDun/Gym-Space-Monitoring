# GSM Implementation Plan

All variable and method names below are the direct Python snake_case translations of the SAD component specifications. All data flows trace the SAD use-case steps exactly.

---

## Video Passing Pattern (`gemini_example.py`)

```python
video_bytes = open(video_file_name, 'rb').read()     # camera → raw bytes
client = genai.Client()
response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents=types.Content(
        parts=[
            types.Part(inline_data=types.Blob(data=video_bytes, mime_type='video/mp4')),
            types.Part(text='<detection prompt here>')
        ]
    )
)
```

- Only for videos < 20 MB (demo `.mp4` qualifies)
- Two `Part`s in one `Content`: the video blob and the text prompt side-by-side
- Response is free-text; each detection module owns its own prompt and parses its own output
- The `MLLMProcessor` is prompt-agnostic — it takes a prompt string and returns the raw response string

---

## Shared Components (Foundation — all phases depend on these)

---

### `backend/sensor/sensor_interface.py`

**SAD spec:**
> Variables: `RawSignal currentSignal`  
> Methods: `normalizeSignal(RawSignal) → Event`

```python
@dataclass
class RawSignal:
    source: str      # "camera" | "wristband" | "equipment" | "entrance"
    data: bytes | dict
    metadata: dict   # zone_id, member_id, timestamp

@dataclass
class Event:
    type: str        # "video" | "biometric" | "location" | "equipment" | "session"
    payload: dict
    zone_id: str
    member_id: str | None
    timestamp: datetime

class SensorInterface:
    current_signal: RawSignal          # SAD: currentSignal

    def normalize_signal(self, raw: RawSignal) -> Event:   # SAD: normalizeSignal(RawSignal)
        ...
```

Routing inside `normalize_signal`:

| `raw.source` | Event `type` | Key `payload` fields |
|---|---|---|
| `"camera"` | `"video"` | `video_bytes`, `mime_type: "video/mp4"` |
| `"wristband"` (with biometric keys) | `"biometric"` | `heart_rate`, `spo2` |
| `"wristband"` (with location keys) | `"location"` | `x`, `y`, `zone_id` |
| `"equipment"` | `"equipment"` | `reps`, `resistance`, `state`, `machine_id` |
| `"entrance"` | `"session"` | `action: "entry"\|"exit"` |

---

### `backend/sensor/sensor_driver.py`

**SAD spec (S Driver):**
> Low-level component communicating with physical sensing hardware and filtering raw signals.

```python
class SensorDriver(ABC):
    def __init__(self, source: str, zone_id: str): ...
    @abstractmethod
    def read(self) -> RawSignal: ...           # single blocking read
    @abstractmethod
    def stream(self) -> Iterator[RawSignal]: ... # continuous stream
```

Concrete implementations (simulation for demo, hardware-swappable):

| Class | `source` | Data produced |
|---|---|---|
| `CameraDriver` | `"camera"` | Reads `.mp4` file as bytes → `RawSignal(data=video_bytes)` |
| `WristbandDriver` | `"wristband"` | Dict with `heart_rate`, `spo2`, `x`, `y`, `member_id` |
| `EquipmentDriver` | `"equipment"` | Dict with `reps`, `resistance`, `state`, `machine_id`, `member_id` |
| `EntranceDriver` | `"entrance"` | Dict with `action`, `member_id` |

`CameraDriver` matches `gemini_example.py` exactly:
```python
video_bytes = open(self.video_path, 'rb').read()
yield RawSignal(source="camera", data=video_bytes, metadata={"zone_id": self.zone_id})
```

---

### `backend/sensor/device_driver.py`

**SAD spec:**
> Variables: `Map<DeviceID, Connection> activeStaffTablets`, `Map<MemberID, Connection> activeWristbands`  
> Methods: `pushToTablet(Alert)`, `pushToWristband(MemberID, Warning)`

```python
@dataclass
class Alert:
    severity: str          # "CRITICAL" | "WARNING" | "INFO"
    zone_id: str
    description: str
    member_id: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    alert_id: str = field(default_factory=lambda: str(uuid4()))
    resolved: bool = False

class DeviceDriver:
    active_staff_tablets: dict[str, Any]    # SAD: activeStaffTablets — WebSocket connections
    active_wristbands: dict[str, Any]       # SAD: activeWristbands — WebSocket connections

    def push_to_tablet(self, alert: Alert) -> None:          # SAD: pushToTablet(Alert)
        # Serializes alert to JSON, broadcasts over WebSocket to all active_staff_tablets

    def push_to_wristband(self, member_id: str, warning: str) -> None:  # SAD: pushToWristband(MemberID, Warning)
        # For demo: logs warning. Real: triggers haptic + screen via wristband connection
```

`Alert` is the single shared dataclass used by every component that produces or consumes alerts.

---

## Phase 1 Components (Due Apr 25)

---

### `backend/controller/system_controller.py`

**SAD spec:**
> Variables: `List<Alert> activeAlerts`  
> Methods: `receiveAlertTrigger(Event)`, `dispatchAlert(Alert)`, `logSystemEvent(Event)`

```python
class SystemController:
    active_alerts: list[Alert]              # SAD: activeAlerts — all live pending alerts

    def receive_alert_trigger(self, event: Event) -> None:
        # SAD: "acts as the primary sink for alert triggers from all monitoring modules"
        # Called by: FallDetection, ConflictDetection, BiometricAnalysis, OccupancyManager
        # Builds Alert from event, adds to active_alerts, calls dispatch_alert()

    def dispatch_alert(self, alert: Alert) -> None:
        # SAD: "routes formatted alert notifications to the Device Driver"
        # Calls: device_driver.push_to_tablet(alert)
        # If biometric warning: also calls device_driver.push_to_wristband(member_id, warning)

    def log_system_event(self, event: Event) -> None:
        # SAD: "forwards real-time event data to the Database Controller for archival"
        # Calls: database_controller.log_alerts(alert) or log_bio_occupancy() depending on type
        # Also called when staff resolves an alert (resolution feedback loop)
```

**Alert resolution feedback loop** (SAD Fall Detection step 8):
> "Staff mark the incident as resolved on their tablet via the Device Driver, which signals the System Controller to log the resolution to the Data Store."

Resolution path: `POST /api/resolve/{alert_id}` → `SystemController.log_system_event(resolved_event)` → `DatabaseController.log_alerts(alert)` → marks resolved in DB, removes from `active_alerts`.

**System Controller is the hub for all alert-producing modules.** Every detector calls `receive_alert_trigger()` — it never calls detectors. The flow always goes:

```
Detector → system_controller.receive_alert_trigger()
         → system_controller.dispatch_alert()
         → device_driver.push_to_tablet()
         → system_controller.log_system_event()
         → database_controller.log_alerts()
```

---

### `backend/db/database_controller.py`

**SAD spec:**
> Variables: `Connection dataStoreConnection`  
> Methods: `logWeightLifting(EquipmentData)`, `logBioOccupancy(BiometricData, OccupancyData)`, `logAlerts(Alert)`, `handleReportQuery(QueryRequest)`

```python
class DatabaseController:
    data_store_connection: Connection       # SAD: dataStoreConnection — SQLAlchemy session

    def log_weight_lifting(self, data: EquipmentData) -> None:
        # SAD: "stores repetition and resistance data from smart machines"

    def log_bio_occupancy(self, biometric: BiometricData, occupancy: OccupancyData) -> None:
        # SAD: "logs continuous wristband telemetry and zone density snapshots"

    def log_alerts(self, alert: Alert) -> None:
        # SAD: "archives resolved system alerts to build historical safety datasets"

    def handle_report_query(self, query: QueryRequest) -> Data:
        # SAD: "retrieves data subsets requested by the Usage Report Generator"
```

---

### `backend/db/models.py`

SQLAlchemy ORM models backing the Data Store:

- `Member(id, name, age, bmi, activity_level, heart_rate_threshold_low, heart_rate_threshold_high)`
- `GymSession(id, member_id, entry_time, exit_time, zone_id)`  — (`Session` reserved by SQLAlchemy)
- `AlertLog(id, alert_id, severity, zone_id, description, member_id, resolved, created_at)`
- `EquipmentUsage(id, member_id, machine_id, zone_id, reps, resistance, started_at)`
- `BiometricSnapshot(id, member_id, heart_rate, spo2, zone_id, timestamp)`
- `OccupancySnapshot(id, zone_id, count, timestamp)`

---

### `backend/main.py`

FastAPI app. Wires together all component instances and runs the WebSocket server:

- `GET /health`
- `WebSocket /ws/alerts` — staff tablet subscribes; `DeviceDriver.push_to_tablet()` broadcasts here
- `POST /api/resolve/{alert_id}` — staff marks resolved → `SystemController.log_system_event()`

---

## Phase 2 Components (Due May 2)

---

### `backend/processing/occupancy_manager.py`

**SAD spec:**
> Variables: `Map<ZoneID, Integer> zoneOccupancyCounts`, `Map<ZoneID, Integer> zoneOccupancyThresholds`  
> Methods: `updateLocationDensity(MemberID, ZoneID)`, `verifyThreshold(ZoneID)`, `triggerAlert(ZoneID)`

```python
class OccupancyManager:
    zone_occupancy_counts: dict[str, int]       # SAD: zoneOccupancyCounts
    zone_occupancy_thresholds: dict[str, int]   # SAD: zoneOccupancyThresholds

    def update_location_density(self, member_id: str, zone_id: str) -> None:
        # SAD: "updates internal tracking of patron distribution based on location signals"
        # Increments zone_occupancy_counts[zone_id], calls verify_threshold()

    def verify_threshold(self, zone_id: str) -> None:
        # SAD: "evaluates current zone occupancy against the maximum allowable density"
        # If count >= threshold: trigger_alert(zone_id)
        # If count >= threshold * 0.8: trigger_alert with INFO severity (approaching)

    def trigger_alert(self, zone_id: str) -> None:
        # SAD: "notifies the System Controller of overcrowding events"
        # Calls: system_controller.receive_alert_trigger(event)
```

Thresholds derived from fire code: 50 sq ft/person minimum. 6,000 sq ft total → ~120 max gym-wide.

---

### `backend/reporting/usage_report_generator.py`

**SAD spec:**
> Accesses historical data from Database Controller to compile management usage reports.

```python
class UsageReportGenerator:
    def generate(self, schedule: str) -> Report:
        # schedule: "hourly" | "daily" | "weekly" | "monthly"
        # Calls: database_controller.handle_report_query(QueryRequest)
        # Returns: Report with occupancy summaries, equipment rankings, density maps
```

---

## Phase 3 Components (Due May 7)

---

### `backend/processing/mllm_processor.py`

**SAD spec:**
> Continuously receives and analyzes video feeds from ceiling cameras. Generates structured text descriptions every 5–10 seconds.

```python
class MLLMProcessor:
    client: genai.Client    # initialized from config (GEMINI_API_KEY)

    def analyze(self, event: Event, prompt: str) -> str:
        # event must be type "video"
        # Passes video_bytes + prompt to Gemini using inline_data pattern
        video_bytes = event.payload["video_bytes"]
        response = self.client.models.generate_content(
            model='gemini-2.0-flash',
            contents=types.Content(
                parts=[
                    types.Part(inline_data=types.Blob(data=video_bytes, mime_type='video/mp4')),
                    types.Part(text=prompt)
                ]
            )
        )
        return response.text
```

The MLLM output is passed to **both** `FallDetection.analyze_mllm_output()` and `ConflictDetection.analyze_mllm_output()` from the same video event — they independently evaluate the same text against their own thresholds.

---

### `backend/processing/fall_detection.py`

**SAD spec:**
> Variables: `String mllmTextOutput`, `float fallConfidence`  
> Methods: `analyzeMLLMOutput(String)`, `triggerAlert(AlertSeverity, ZoneID)`

```python
FALL_PROMPT = (
    "Analyze this gym footage for fall events. Has anyone collapsed or fallen to the ground? "
    "Respond only in this format — Fall: <1-10>, Confidence: <1-10>"
)

class FallDetection:
    mllm_text_output: str      # SAD: mllmTextOutput — latest MLLM response
    fall_confidence: float     # SAD: fallConfidence — threshold to confirm a fall (default: 6.0)

    def analyze_mllm_output(self, mllm_text_output: str) -> None:
        # SAD: "identifies patterns in MLLM data indicating a patron has collapsed"
        # Parses "Fall: X" from text, compares against fall_confidence
        # If score >= fall_confidence: trigger_alert(CRITICAL, zone_id)
        # If 4 <= score < fall_confidence: trigger_alert(WARNING, zone_id) — inconclusive

    def trigger_alert(self, severity: str, zone_id: str) -> None:
        # SAD: "passes high-priority fall events and location data to the System Controller"
        # Calls: system_controller.receive_alert_trigger(event)
```

---

### `backend/processing/conflict_detection.py`

**SAD spec:**
> Variables: `String mllmTextOutput`, `float conflictConfidence`  
> Methods: `analyzeMLLMOutput(String)`, `triggerAlert(AlertSeverity, ZoneID)`

```python
CONFLICT_PROMPT = (
    "Analyze this gym footage for member conflict. Is there any aggressive or threatening "
    "physical behavior between patrons? "
    "Respond only in this format — Conflict: <1-10>, Confidence: <1-10>"
)

class ConflictDetection:
    mllm_text_output: str         # SAD: mllmTextOutput
    conflict_confidence: float    # SAD: conflictConfidence — threshold (default: 6.0)

    def analyze_mllm_output(self, mllm_text_output: str) -> None:
        # SAD: "parses processed video descriptions to identify altercations or threats"
        # If score >= conflict_confidence: trigger_alert(CRITICAL, zone_id)
        # If 4 <= score < conflict_confidence: trigger_alert(WARNING, zone_id)

    def trigger_alert(self, severity: str, zone_id: str) -> None:
        # SAD: "dispatches confirmed conflict metadata to the System Controller"
        # Calls: system_controller.receive_alert_trigger(event)
```

---

### `backend/processing/biometric_analysis.py`

**SAD spec:**
> Variables: `float heartRateThresholdLow`, `float heartRateThresholdHigh`, `HealthProfile currentProfile`  
> Methods: `evaluateHeartRate(float, HealthProfile) → BiometricStatus`, `triggerAlert(BiometricStatus, MemberID, ZoneID)`

```python
@dataclass
class HealthProfile:
    member_id: str
    age: int
    bmi: float
    activity_level: str
    heart_rate_threshold_low: float     # SAD: heartRateThresholdLow
    heart_rate_threshold_high: float    # SAD: heartRateThresholdHigh

class BiometricStatus(Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"

class BiometricAnalysis:
    heart_rate_threshold_low: float     # SAD: heartRateThresholdLow
    heart_rate_threshold_high: float    # SAD: heartRateThresholdHigh
    current_profile: HealthProfile      # SAD: currentProfile — loaded from DB on session start

    def evaluate_heart_rate(self, current_heart_rate: float, profile: HealthProfile) -> BiometricStatus:
        # SAD: "assesses live heart rate readings against stored personal thresholds"
        # Returns BiometricStatus based on comparison to profile thresholds

    def trigger_alert(self, status: BiometricStatus, member_id: str, zone_id: str) -> None:
        # SAD: "issues a Warning Alert to the System Controller when abnormalities detected"
        # Calls: system_controller.receive_alert_trigger(event)
        # SystemController.dispatch_alert() will then call BOTH push_to_tablet AND push_to_wristband
```

---

## Complete Data Flows (matching SAD use-case steps exactly)

### Fall Detection
```
CameraDriver.stream()
  → RawSignal(source="camera", data=video_bytes, metadata={zone_id})
  → SensorInterface.normalize_signal()                           # SAD step 2
  → Event(type="video", payload={video_bytes, mime_type})
  → MLLMProcessor.analyze(event, FALL_PROMPT)                   # SAD step 3
  → mllm_text_output = "Fall: 8, Confidence: 9"
  → FallDetection.analyze_mllm_output(mllm_text_output)         # SAD step 4
    (score=8.0 >= fall_confidence=6.0 → CRITICAL)
  → FallDetection.trigger_alert(CRITICAL, zone_id)              # SAD step 5
  → SystemController.receive_alert_trigger(event)
  → SystemController.dispatch_alert(Alert(CRITICAL, ...))       # SAD step 6
  → DeviceDriver.push_to_tablet(alert)                          # SAD step 7
  → WebSocket broadcast → Staff Tablet

  [On resolution] Staff → POST /api/resolve/{alert_id}          # SAD step 8
  → SystemController.log_system_event(resolved_event)
  → DatabaseController.log_alerts(alert)
```

### Abnormal Heart Rate
```
WristbandDriver.stream()
  → RawSignal(source="wristband", data={heart_rate: 180, member_id})   # SAD step 1
  → SensorInterface.normalize_signal()                                  # SAD step 2
  → Event(type="biometric", ...)
  → BiometricAnalysis.evaluate_heart_rate(180, profile)                 # SAD step 3
    (180 > heart_rate_threshold_high → WARNING)
  → BiometricAnalysis.trigger_alert(WARNING, member_id, zone_id)        # SAD step 4
  → SystemController.receive_alert_trigger(event)
  → SystemController.dispatch_alert(Alert(WARNING, ...))                # SAD step 5
  → DeviceDriver.push_to_tablet(alert)               ─┐                 # SAD step 6
  → DeviceDriver.push_to_wristband(member_id, msg)   ─┘ simultaneous
```

### Overcrowding
```
WristbandDriver.stream()
  → RawSignal(source="wristband", data={x, y, zone_id, member_id})
  → SensorInterface.normalize_signal()
  → Event(type="location", ...)
  → OccupancyManager.update_location_density(member_id, zone_id)   # SAD step 1
  → OccupancyManager.verify_threshold(zone_id)                     # SAD step 3
    (count >= zone_occupancy_thresholds[zone_id])
  → OccupancyManager.trigger_alert(zone_id)                        # SAD step 4
  → SystemController.receive_alert_trigger(event)
  → SystemController.dispatch_alert(Alert(WARNING, ...))           # SAD step 5
  → DeviceDriver.push_to_tablet(alert)                             # SAD step 6
```

### Conflict Detection
```
CameraDriver.stream()                                              # SAD step 1
  → SensorInterface.normalize_signal()
  → Event(type="video", ...)
  → MLLMProcessor.analyze(event, CONFLICT_PROMPT)                 # SAD step 2
  → mllm_text_output = "Conflict: 7, Confidence: 8"
  → ConflictDetection.analyze_mllm_output(mllm_text_output)       # SAD step 3
  → ConflictDetection.trigger_alert(CRITICAL, zone_id)            # SAD step 4
  → SystemController.receive_alert_trigger(event)
  → SystemController.dispatch_alert(Alert(CRITICAL, ...))
  → DeviceDriver.push_to_tablet(alert)                            # SAD step 5
```

*Note: Fall and Conflict run on the same video event — MLLMProcessor output goes to both detectors.*

### Equipment Usage Reporting
```
EquipmentDriver.stream()                                           # SAD step 1
  → RawSignal(source="equipment", data={reps, resistance, state})
  → SensorInterface.normalize_signal()
  → Event(type="equipment", ...)
  → DatabaseController.log_weight_lifting(EquipmentData)          # SAD step 2
  → Data Store

  [Scheduled report]
  → UsageReportGenerator.generate("daily")                        # SAD step 4
  → DatabaseController.handle_report_query(QueryRequest)          # SAD step 5
  → Report → Management Dashboard                                 # SAD step 6
```

*Equipment data flows directly to DatabaseController — no System Controller involvement.  
This is the observational pipeline, not the alerting pipeline.*

---

## SAD Component-to-File Mapping

| SAD Component | File | Phase |
|---|---|---|
| Sensor Interface | `backend/sensor/sensor_interface.py` | Shared |
| S Driver (Sensor Driver) | `backend/sensor/sensor_driver.py` | Shared |
| D Driver (Device Driver) | `backend/sensor/device_driver.py` | Shared |
| System Controller | `backend/controller/system_controller.py` | Phase 1 |
| Database Controller | `backend/db/database_controller.py` | Phase 1 |
| Data Store (ORM models) | `backend/db/models.py` | Phase 1 |
| FastAPI app | `backend/main.py` | Phase 1 |
| Occupancy Manager | `backend/processing/occupancy_manager.py` | Phase 2 |
| MLLM Usage Report Generator | `backend/reporting/usage_report_generator.py` | Phase 2 |
| MLLM Processor | `backend/processing/mllm_processor.py` | Phase 3 |
| Fall Detection | `backend/processing/fall_detection.py` | Phase 3 |
| Conflict Detection | `backend/processing/conflict_detection.py` | Phase 3 |
| Biometric Analysis | `backend/processing/biometric_analysis.py` | Phase 3* |

*Biometric Analysis not on SAD timeline but doesn't require MLLM; can stub in Phase 1 and complete with Phase 3.
