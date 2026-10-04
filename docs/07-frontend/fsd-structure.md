---
id: fsd-structure
domain: frontend
tags:
  - feature-sliced-design
  - folder-structure
  - layers
  - features
  - shared
  - enums
related:
  - frontend-architecture
  - pages
  - auth-flow
  - upload-ui
---

# FSD Project Structure

## Overview

The frontend follows **Feature-Sliced Design (FSD)** methodology. The `src/` directory is organized into layers with clear boundaries and unidirectional dependencies:

```
app        → providers, routing (top-level composition)
features   → business features (auth, dashboards, upload, users, admin)
shared     → reusable infrastructure (API client, components, types)
```

**Dependency rule:** `app` → `features` → `shared`. Lower layers must never import from higher layers.

## Complete Folder Tree

```
frontend/
├── public/
│   └── (static assets)
├── src/
│   ├── main.tsx                          # Entry point
│   ├── react-plotly.d.ts                 # Plotly.js type declarations
│   │
│   ├── app/                              # Application composition layer
│   │   ├── providers.tsx                 # QueryClient, Router, Theme, Toaster
│   │   └── routes.tsx                    # Route definitions with access control
│   │
│   ├── features/                         # Business features
│   │   │
│   │   ├── auth/                         # Authentication feature
│   │   │   ├── index.ts                  # Public API exports
│   │   │   ├── api/
│   │   │   │   └── authApi.ts            # login, registerRequest, getProfile, logoutClient
│   │   │   ├── model/
│   │   │   │   ├── authToken.ts          # Token storage (memory / sessionStorage)
│   │   │   │   └── useAuth.ts            # Auth state hook (user, login, logout)
│   │   │   └── ui/
│   │   │       ├── LoginForm.tsx         # Login page form
│   │   │       └── RegisterForm.tsx      # Registration request form
│   │   │
│   │   ├── dashboards/                   # Dashboard viewing feature
│   │   │   ├── index.ts                  # Public API exports
│   │   │   ├── api/
│   │   │   │   └── dashboardApi.ts       # Dashboard data fetching
│   │   │   ├── model/                    # (empty — state via TanStack Query)
│   │   │   └── ui/
│   │   │       ├── DashboardList.tsx     # Dashboard list page (DataGrid table)
│   │   │       ├── DashboardView.tsx     # Single dashboard view with charts + UploadModal
│   │   │       ├── DashboardFilters.tsx  # Filter panel component
│   │   │       └── charts/
│   │   │           ├── index.ts          # Chart exports
│   │   │           ├── ChartRenderer.tsx # Main renderer with data conversion logic
│   │   │           ├── LineChart.tsx     # Line chart (Plotly.js)
│   │   │           ├── PlotlyChart.tsx   # Generic Plotly wrapper
│   │   │           └── TableChart.tsx    # Table chart
│   │   │
│   │   ├── upload/                       # File upload feature
│   │   │   ├── index.ts                  # Public API exports
│   │   │   ├── api/
│   │   │   │   └── uploadApi.ts          # File upload and processing status
│   │   │   └── ui/
│   │   │       ├── UploadModal.tsx       # Upload modal dialog (opened from DashboardView)
│   │   │       └── FileDropzone.tsx      # Drag-and-drop file selector
│   │   │
│   │   ├── users/                        # User profile feature
│   │   │   ├── index.ts                  # Public API exports
│   │   │   ├── api/
│   │   │   │   └── userApi.ts            # Profile, change password, delete account
│   │   │   └── ui/
│   │   │       ├── UserProfile.tsx       # Profile page (email, role, actions)
│   │   │       └── ChangePasswordPage.tsx # Password change form
│   │   │
│   │   └── admin/                        # Admin panel feature
│   │       ├── api/
│   │       │   └── adminApi.ts           # Admin API calls
│   │       └── ui/
│   │           ├── AdminPanel.tsx        # Tabbed admin panel container (state-preserving)
│   │           ├── UserManagement.tsx    # User CRUD with inline editing
│   │           ├── RegistrationRequests.tsx # Approve/reject registration requests
│   │           ├── DashboardManagement.tsx  # Dashboard CRUD
│   │           └── LogViewer.tsx         # Processing log viewer
│   │
│   └── shared/                           # Shared infrastructure layer
│       ├── api/
│       │   ├── index.ts                  # API exports
│       │   └── axiosInstance.ts          # Axios instance with interceptors
│       │
│       ├── components/
│       │   ├── index.ts                  # Component exports
│       │   ├── Layout/
│       │   │   ├── index.ts              # Layout exports
│       │   │   ├── AppLayout.tsx         # Main application layout wrapper (Header + Outlet)
│       │   │   └── Header.tsx            # Top navigation bar (role-based items, user menu, logout)
│       │   ├── NotFound.tsx              # 404 page
│       │   ├── PlaceholderPage.tsx       # Placeholder for unimplemented pages
│       │   ├── ProtectedRoute.tsx        # Auth guard (redirects to /login)
│       │   ├── RoleBasedAccess.tsx       # Role-based component visibility
│       │   ├── ConfirmDialog.tsx         # Reusable confirmation dialog for destructive actions
│       │   └── AccessDenied.tsx          # "No access" display component
│       │
│       ├── hooks/
│       │   └── useConfirmDialog.ts       # Hook for imperative ConfirmDialog control
│       │
│       ├── utils/
│       │   └── shortUuid.ts              # Short UUID utility (first 8 chars for display)
│       │
│       └── types/
│           ├── api.types.ts              # API response/request type definitions
│           ├── enums.ts                  # Frontend enum constants (mirrors backend StrEnum)
│           └── formSchemas.ts            # Zod validation schemas for all forms
│
├── package.json
└── vite.config.ts
```

## Layer Responsibilities

### `app/` — Application Composition

- **Purpose:** Wires together all providers and defines the routing table.
- **Files:** `providers.tsx` (composition root), `routes.tsx` (route definitions).
- **Rules:** This layer knows about all features but contains no business logic.

### `features/` — Business Features

Each feature is a self-contained vertical slice with four sublayers:

| Sublayer | Purpose |
| --- | --- |
| `api/` | API call functions (Axios requests to specific endpoints) |
| `model/` | Business logic hooks and state management for the feature |
| `ui/` | React components (pages, forms, sub-components) |
| `index.ts` | Public API — only exports that other features may import |

**Feature dependency rule:** Features should not import from each other's `model/` or `ui/` sublayers. Cross-feature communication happens through `shared/` or the `app/` layer.

### `shared/` — Reusable Infrastructure

| Sublayer | Purpose |
| --- | --- |
| `api/` | Shared Axios instance with interceptors |
| `components/` | Generic UI components (layout, guards, dialogs, utilities) |
| `hooks/` | Reusable React hooks (e.g., `useConfirmDialog`) |
| `utils/` | Utility functions (e.g., `shortUuid`) |
| `types/` | Shared TypeScript types, enums, and Zod schemas |

**Rules:** `shared/` must never import from `features/` or `app/`.

## Component Architecture

### Shared Components

The following shared components are available for use across features:

| Component | Purpose | Usage |
| --- | --- | --- |
| `PlaceholderPage` | Stub for unimplemented routes | Use for routes that exist in navigation but lack full implementation |
| `AccessDenied` | Permission denial display | Role-based access denial (403), route-level access denial |
| `NotFound` | 404 page | Unmatched routes (`*` path) |
| `ProtectedRoute` | Auth guard | Redirects unauthenticated users to `/login` |
| `RoleBasedAccess` | Role-based visibility | Renders children only for users with specified roles; defaults to `<AccessDenied />` fallback |
| `ConfirmDialog` | Destructive action confirmation | Delete user/dashboard, reject registration — invoked via `useConfirmDialog` hook |
| `ErrorBoundary` | Component-level error isolation | Catches render errors in component subtrees |
| `ErrorPage` | Error state pages | Variant-based error pages (e.g., 500) |

### PlaceholderPage Usage Guidelines

Use `PlaceholderPage` when:
- A route exists in navigation but the page is not yet implemented
- Developing a new feature and need a stub during development

Do NOT use when:
- An action within an existing page is not implemented (use disabled button + tooltip instead)
- A 404 should be shown (use `NotFound`)
- Permission denial (use `AccessDenied`)

### AccessDenied Integration

`AccessDenied` serves as the default fallback for `RoleBasedAccess`. When a non-admin user accesses `/admin`, they see "No access — contact your administrator" instead of a blank page. The component is also appropriate for inline permission denial on individual dashboards.

### Chart Component Placement

Chart components (`LineChart`, `TableChart`, `ChartRenderer`, `PlotlyChart`) reside in `features/dashboards/ui/charts/` — they are dashboard-specific UI components tightly coupled to dashboard data models (`GraphDataWithConfig`). A standalone `features/charts/` module is not warranted because:
- Chart components are presentation-layer elements scoped to dashboard visualization
- No standalone chart features (export, templates, embedding) currently exist
- Chart functionality is fully contained within the dashboard rendering pipeline
- All chart types (bar, pie, line, table) are rendered through `ChartRenderer`, which delegates to `PlotlyChart` (for bar/pie), `LineChart` (for line), and `TableChart` (for table)

### Dashboard-Focused Charts Directory

```
features/dashboards/ui/charts/
├── index.ts          # Barrel export (PlotlyChart, ChartRenderer)
├── ChartRenderer.tsx # Main renderer with data conversion logic
├── LineChart.tsx     # Line chart component
├── PlotlyChart.tsx   # Generic Plotly wrapper
└── TableChart.tsx    # HTML table rendering
```

## Enum Synchronization

The frontend does **not** mirror the backend enum surface wholesale. `src/mkobi/models/enums.py` declares **20** `StrEnum` classes; `shared/types/enums.ts` declares **10** families. **Nine** of those ten mirror a backend class one-for-one — `UserRole`, `DashboardPermission`, `GraphType`, `FilterType`, `RegistrationStatus`, `UploadMode`, `ProcessingStatus`, `BarmodeEnum` and `ErrorCode`. The tenth, `FileUploadStatus`, is **client-only** and has no backend counterpart.

The remaining **11** backend classes are deliberately **not** mirrored, either because nothing on the client consumes them or because they are backend presentation vocabulary with no client counterpart — `ButtonVariant` and `ComponentSize` among them, which the server does not enforce (see [`SPEC.md`](../SPEC.md) row `3.42`). That leaves **9 mirrored + 11 unmirrored = 20**.

The asymmetry is **two-directional** and is now declared, not implied. Two named allow-lists live beside the mirrors in `frontend/src/shared/types/enums.ts`:

| Allow-list             | Contents                | Meaning                                                                                                    |
| ---------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------- |
| `SERVER_ONLY_FAMILIES` | 11 backend class names | A backend `StrEnum` with no mirror, recorded so the absence is an explicit decision rather than an oversight. |
| `CLIENT_ONLY_FAMILIES` | `FileUploadStatus`      | A frontend family with no backend counterpart.                                                              |

`shared/types/__tests__/enums.test.ts` asserts **exact sets** in both directions rather than membership: every member of every mirrored family matches the backend, every unmirrored backend class appears in `SERVER_ONLY_FAMILIES`, every client-only family appears in `CLIENT_ONLY_FAMILIES`, and neither allow-list may name a mirrored family. A newly added family on either tier therefore fails the suite until its placement is declared.

The frontend uses `as const` objects with derived union types instead of TypeScript enums for `erasableSyntaxOnly` compatibility.

## Cross-References

- [Frontend Architecture](architecture.md) — System context, principles, and data flow
- [Pages](pages.md) — UI pages mapped to these features
- [Auth Flow](auth-flow.md) — Detailed auth feature documentation
- [Upload UI](upload-ui.md) — Upload modal feature and API integration
- [Frontend Security](frontend-security.md) — Security measures across all features
