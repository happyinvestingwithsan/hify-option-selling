# HIFY Option Selling — VS Code Separate Terminal Run Commands

Run the **Backend** and **Frontend** in two separate PowerShell terminals inside VS Code (`D:\AI Projects\Trading Log\OptionSelling`).

---

## Terminal 1: Backend (FastAPI on `0.0.0.0:8000`)

### Development Mode (Auto-Reload)
```powershell
cd "D:\AI Projects\Trading Log\OptionSelling\backend"
.\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Production Mode (No Reload)
```powershell
cd "D:\AI Projects\Trading Log\OptionSelling\backend"
.\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000
```

- **Swagger API Docs:** `http://localhost:8000/docs`
- **Health Check:** `http://localhost:8000/health`

---

## Terminal 2: Frontend (Next.js on `0.0.0.0:3011`)

### Development Mode
```powershell
cd "D:\AI Projects\Trading Log\OptionSelling\frontend"
npm run dev -- -H 0.0.0.0 -p 3011
```

### Production Mode
```powershell
cd "D:\AI Projects\Trading Log\OptionSelling\frontend"
npm run build
npm run start -- -H 0.0.0.0 -p 3011
```

- **Desktop App:** `http://localhost:3011`
- **Mobile (Tailscale):** `http://<your-tailscale-100.x.x.x-ip>:3011`

---

## One-Click Launcher (Alternative)
From the root folder (`D:\AI Projects\Trading Log\OptionSelling`):
```powershell
.\start.ps1
```
*(Or `.\start.ps1 -Production` for production mode.)*

---

## Quick Verification Commands
```powershell
# Backend tests
cd "D:\AI Projects\Trading Log\OptionSelling"
.\backend\.venv\Scripts\pytest.exe backend/tests -v

# Frontend type-check & build
cd "D:\AI Projects\Trading Log\OptionSelling\frontend"
npx tsc --noEmit
npm run build
```
