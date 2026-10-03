---
id: swagger-guide
domain: reference
tags:
  - swagger
  - api
  - documentation
  - authentication
  - testing
  - fastapi
related:
  - run-guide
  - system-overview
  - auth-api
  - dashboards-api
  - backend-architecture
---

# Working with Swagger UI at http://localhost:8010/docs/

## Overview

FastAPI provides automatic interactive API documentation using Swagger UI. This allows you to test all API endpoints directly from your browser without needing external tools like curl or Postman.

Base URL: `http://localhost:8010/docs/`

**Tier scope.** This guide describes a development-tier workflow. When
`ENV=production` the application sets `docs_url`, `redoc_url` and
`openapi_url` to `None`, so `/docs`, `/redoc` and `/openapi.json` all return
`404` from the application. In the shipped production topology the real control
is nginx, which proxies only `/api` and the health paths and serves the SPA for
everything else — see
[Deployment](../10-deployment/deployment.md#where-the-api-documentation-surface-is-protected-in-production).

## Getting Started

### 1. Start the Application

Make sure your application is running:

```bash
# Using Docker
docker-compose up -d

# Or directly
uv run uvicorn src.mkobi.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Open Swagger UI

Open your browser and navigate to:
```
http://localhost:8010/docs/
```

You should see the interactive API documentation with all available endpoints organized by tags.

## Authentication

Most endpoints require authentication. Here's how to authorize:

### Step 1: Login to Get Token

1. Find the **"auth"** section in Swagger UI
2. Expand **"POST /api/v1/auth/login"**
3. Click **"Try it out"**
4. Enter credentials in the request body:
   ```json
   {
     "email": "admin@example.com",
     "password": "your_password"
   }
   ```
5. Click **"Execute"**
6. Copy the `access_token` value from the response (without quotes)

### Step 2: Authorize Swagger UI

1. Click the **"Authorize"** button at the top of the page
2. In the `HTTPBearer` section, enter your token:
   ```
   Bearer YOUR_ACCESS_TOKEN_HERE
   ```
   (Note: Include the word "Bearer" followed by a space, then your token)
3. Click **"Authorize"** and then **"Close"**

Now you can access all protected endpoints!

## Testing Layout API

After completing TASK_012 and TASK_016, the Layout API should be fully functional. Here's how to test it:

### List All Layouts (GET /api/v1/layouts)

1. Find the **"layouts"** section
2. Expand **"GET /api/v1/layouts"**
3. Click **"Try it out"**
4. Click **"Execute"**
5. Expected response: **200 OK** with array of layouts

### Create Layout (POST /api/v1/layouts)

1. Expand **"POST /api/v1/layouts"**
2. Click **"Try it out"**
3. Enter in the request body:
   ```json
   {
     "name": "test_layout",
     "definition": {
       "grid": [
         {"columns": [{"graph_id": "g1", "width": 12}]
       ],
       "graphs": [
         {"id": "g1", "type": "bar", "title": "Sample Chart"}
       ]
     }
   }
   ```
4. Click **"Execute"**
5. Expected response: **201 Created** with created layout data

### Get Layout by ID (GET /api/v1/layouts/{layout_id})

1. Expand **"GET /api/v1/layouts/{layout_id}"**
2. Click **"Try it out"**
3. Paste the layout ID in the `layout_id` field (copy from the list above)
4. Click **"Execute"**
5. Expected response: **200 OK** with layout data

### Update Layout (PUT /api/v1/layouts/{layout_id})

1. Expand **"PUT /api/v1/layouts/{layout_id}"**
2. Click **"Try it out"**
3. Enter the layout ID
4. Enter in the request body:
   ```json
   {
     "name": "updated_layout_name"
   }
   ```
   (Note: Only specify fields you want to update)
5. Click **"Execute"**
6. Expected response: **200 OK** with updated layout data

### Delete Layout (DELETE /api/v1/layouts/{layout_id})

1. Expand **"DELETE /api/v1/layouts/{layout_id}"**
2. Click **"Try it out"**
3. Enter the layout ID
4. Click **"Execute"**
5. Expected response: **204 No Content**

## Other Useful Endpoints

### Health Check
- **GET /health** - Check application health
- **GET /health/detailed** - Detailed health with database status

### Authentication
- **POST /api/v1/auth/login** - Login and get JWT token
- **POST /api/v1/auth/register-request** - Request registration
- **GET /api/v1/auth/me** - Get current user info

### Dashboards
- **GET /api/v1/dashboards/my** - List user's dashboards
- **GET /api/v1/dashboards/** - List all dashboards (admin)
- **POST /api/v1/dashboards/** - Create dashboard (admin)
- **GET /api/v1/dashboards/{id}** - Get dashboard details
- **PUT /api/v1/dashboards/{id}** - Update dashboard (admin)
- **DELETE /api/v1/dashboards/{id}** - Delete dashboard (admin)

### Collection paths
The four collection endpoints below are declared — and served — with a trailing
slash. A request without the slash is **not** redirected; it answers `404`, the
same as an undeclared path, so an unauthenticated caller cannot enumerate which
collection paths exist.
- **GET /api/v1/users/** - List all users (admin)
- **POST /api/v1/users/** - Create user (admin)
- **GET /api/v1/graphs/** - List graphs available to the user
- **POST /api/v1/graphs/** - Create graph (admin)
- **GET /api/v1/admin/logs/** - List processing logs (admin)

### Data
- **GET /api/v1/data/aggregated** - Get aggregated data for charts
- **POST /api/v1/upload/{dashboard_id}** - Upload CSV data (editor+)

## Troubleshooting

### 405 Method Not Allowed
If you get 405 errors on layout endpoints, ensure:
1. The layouts router is registered in `src/mkobi/app.py`
2. The routes in `src/mkobi/api/routes/layouts.py` don't have leading slashes (use `""` not `"/"`)

### 500 Internal Server Error
If updates return 500:
1. Check that `LayoutUpdate` model uses proper PATCH-style updates
2. Ensure `None` values don't overwrite existing data
3. Check `src/mkobi/services/layout_service.py` uses `model_dump(exclude_unset=True)`

### Authentication Issues
- **401 Unauthorized**: Token missing or invalid
- **403 Forbidden**: Token valid but insufficient permissions

## Tips

1. **Use "Try it out"** - Each endpoint has a "Try it out" button for interactive testing
2. **Check response codes** - Successful operations return:
   - 200: Success (GET, PUT)
   - 201: Created (POST)
   - 204: No Content (DELETE)
3. **View schemas** - Click on model names to see request/response schemas
4. **Export** - In the development tier you can export API definitions in OpenAPI format; in production the schema surface is closed (see the tier scope above)

## Project Structure

The API implementation follows Clean Architecture:
- `src/mkobi/api/routes/` — API route handlers per domain (auth, dashboards, layouts, graphs, filters, upload, admin, client-errors)
- `src/mkobi/services/` — Business logic services
- `src/mkobi/db/repositories/` — Data access layer
- `src/mkobi/models/` — Pydantic models for request/response validation
- `src/mkobi/db/models/` — SQLAlchemy ORM models
