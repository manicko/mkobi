---
id: upload-ui
domain: frontend
tags:
  - file-upload
  - csv
  - react-dropzone
  - upload-modes
  - processing-status
  - api-integration
  - file-validation
  - modal-dialog
related:
  - frontend-security
  - processing-api
  - pages
  - frontend-architecture
---

# Upload UI

## Overview

The upload feature (`features/upload/`) provides the UI and API integration for uploading CSV and CSV.gz files to a dashboard. Upload is implemented as a **modal dialog** (`UploadModal`) opened from the DashboardView page, rather than a separate page. This eliminates page navigation during upload and provides a smoother user experience.

**Access:** Restricted to users with `admin` or `editor` roles. The "Upload Data" button is only visible to these roles on the DashboardView page.

## Upload Modal

**Component:** `features/upload/ui/UploadModal.tsx`

The `UploadModal` is a reusable dialog component that accepts `open`, `onClose`, `dashboardId`, and `onUploadComplete` props. It is rendered inside `DashboardView` and opened via the "Upload Data" button.

### UI Elements

| Element | Type | Description |
| --- | --- | --- |
| Mode toggle | `ToggleButtonGroup` | "Overwrite" (reset all data) / "Append" (add new rows) |
| File dropzone | `FileDropzone` | Drag-and-drop area; accepts `.csv` and `.csv.gz` |
| File list | List | Selected files with remove buttons and file sizes |
| Upload queue | Paper section | Per-file progress bars with status indicators |
| Start Upload button | `Button` | Begins sequential upload of all files; disabled while uploading |
| Cancel/Close button | `Button` | Closes the modal; disabled while uploading, labeled "Close" when complete |
| Success alert | `Alert` | Shown when all files are processed successfully |

### Upload Modes

| Mode | Enum Value | Description |
| --- | --- | --- |
| Overwrite | `UploadMode.OVERWRITE` | Replaces all existing aggregated data for the dashboard |
| Append | `UploadMode.APPEND` | Adds new data rows to existing aggregated data |

## File Dropzone

**Component:** `features/upload/ui/FileDropzone.tsx`

Built on `react-dropzone` with the following configuration:

### Accepted File Types

- **Extensions:** `.csv`, `.csv.gz`
- **MIME types:** `text/csv`, `application/gzip`, `application/x-gzip`

### Client-Side Validation

1. **MIME type check:** Files are filtered by MIME type via the dropzone `accept` prop.
2. **Extension check:** Additional validation ensures the filename ends with `.csv` or `.csv.gz`.
3. **Rejection handling:** Invalid files trigger a toast error message.

### UI States

- **Idle:** "Drag & drop files here, or click to select"
- **Drag active:** Border and background highlight changes; "Drop files here..."
- **Files selected:** File list with name, size, and remove button for each file

## Upload Flow

```
User clicks "Upload Data" on DashboardView
        │
        ▼
UploadModal opens (Dialog)
        │
        ▼
User selects mode (overwrite/append)
        │
        ▼
User drags/drops files onto dropzone
        │
        ▼
Client validates file extensions and MIME types
        │
        ▼
Files appear in the upload queue
        │
        ▼
User clicks "Start Upload"
        │
        ▼
For each file:
  ┌─────────────────────────────────┐
  │ POST /api/v1/upload/:dashboard_id│
  │ Query: mode=overwrite|append     │
  │ Body: multipart/form-data        │
  │ Progress: tracked via callback   │
  └────────────────┬────────────────┘
                   │
                   ▼
  On success: { task_id, filename, dashboard_id, status: "uploaded", message, uploaded_at }
  On failure: error toast, file marked as ERROR
                   │
                   ▼
All files uploaded → poll processing status
        │
        ▼
GET /api/v1/upload/status/:task_id (polled via TanStack Query)
        │
        ▼
Status = 'completed'
  → toast success → onUploadComplete callback → modal closes
  → dashboard data invalidated and refetched
```

**Key difference from page-based flow:** There is no page navigation. The modal stays open during upload, shows progress inline, and closes automatically (or user clicks "Close") when processing is complete. Dashboard data refreshes via TanStack Query invalidation.

## API Integration

**Module:** `features/upload/api/uploadApi.ts`

| Function | Method | Endpoint | Description |
| --- | --- | --- | --- |
| `uploadFile` | `POST` | `/api/v1/upload/:dashboard_id` | Uploads a file with progress callback; query param `mode` |
| `useProcessingStatus` | `GET` | `/api/v1/upload/status/:task_id` | TanStack Query hook for polling processing status |

### Upload Request

```
POST /api/v1/upload/:dashboard_id?mode=overwrite
Content-Type: multipart/form-data
Authorization: Bearer <token>

File: <binary data>
```

**Response** (`200 OK`):
```json
{
  "task_id": "<uuid>",
  "filename": "data.csv",
  "dashboard_id": "<uuid>",
  "status": "uploaded",
  "message": "File uploaded successfully",
  "uploaded_at": "2026-05-31T12:00:00Z"
}
```

### Processing Status Polling

After all files are uploaded, the modal polls for processing status:

```
GET /api/v1/upload/status/:task_id
```

**Response:**
```json
{
  "task_id": "<uuid>",
  "status": "processing",
  "message": "Aggregating data..."
}
```

Polling continues until `status` is `'completed'` (or `'failed'`), at which point a success toast is shown and the `onUploadComplete` callback invalidates the dashboard data cache. A mid-job `'processing'` value is non-terminal and keeps the poll running.

## Backend Processing Pipeline

Once the file is uploaded, the backend executes the full processing pipeline:

```
Upload → Parse (Polars) → Transform (LoaderConfig) → Aggregate → Save to PostgreSQL
```

**Important:** Each upload triggers a **full recalculation** of aggregates for the dashboard. There is no incremental aggregation.

### Processing Status Lifecycle

| Status | Description |
| --- | --- |
| `started` | Task created, file upload initiated |
| `uploaded` | File saved to temporary storage, not yet picked up by a worker |
| `processing` | Pipeline execution in progress |
| `completed` | Processing completed successfully |
| `failed` | Processing encountered an error |

**Renderer note.** The modal stores the polled status into `FileUploadState.processingStatus` but no render branch reads it; the visible state comes from `FileUploadState.status` (`FileUploadStatus`: `PENDING`, `UPLOADING`, `SUCCESS`, `ERROR`). The mapping reacts to only two polled values (`failed` → `ERROR`, `completed` → success toast) and the progress bar uses the axios upload percentage, not `statusData.progress`. The `processing` state (now genuinely observable mid-job, with `progress=50`) is therefore non-terminal and rendered as the pre-existing "Success" display; `useProcessingStatus` simply keeps polling until `completed` or `failed`.

## File Upload Security

### Client-Side Checks

- File extension validation (`.csv`, `.csv.gz` only).
- MIME type filtering via `react-dropzone` accept configuration.
- User feedback via toast notifications for rejected files.

### Server-Side Enforcement

The backend independently enforces:

- **MIME type validation:** Only `text/csv`, `application/gzip`, `application/x-gzip` are accepted.
- **File size limit:** Maximum file size is enforced on the backend.
- **Rate limiting:** Upload endpoints are rate-limited.
- **Temporary file cleanup:** Files are deleted from temporary storage after processing.

**Note:** Client-side validation is a UX convenience. The backend is the security boundary — all validation is enforced server-side regardless of client behavior.

## Cross-References

- [Frontend Security](frontend-security.md) — File upload security details
- [Processing API](../../03-processing/processing-api.md) — Backend upload and processing endpoints
- [Pages](pages.md) — DashboardView page with integrated upload modal
- [Data Flow](../../00-overview/data-flow.md) — End-to-end upload-to-display pipeline
- [Task Queue](../../03-processing/task-queue.md) — Background processing architecture
