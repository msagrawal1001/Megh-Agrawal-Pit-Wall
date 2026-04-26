# F1 Pit Wall Dashboard 🏁

A real-time Formula 1 dashboard with live standings, race results, and calendar — **no server required**.

![F1 2026](https://img.shields.io/badge/F1-2026-FF8000?style=flat&logo=formula-1)
![GitHub Pages](https://img.shields.io/badge/Deploy-GitHub%20Pages-181717?style=flat&logo=github)
![API](https://img.shields.io/badge/Data-Jolpi.ca-28A745?style=flat)

## Live Demo

See it in action at: `https://YOUR_USERNAME.github.io/f1-pit-wall/`

## Features

- **Live Driver Standings** — Top 10 with real-time points
- **Constructor Standings** — All 11 teams with progress bars
- **Race Calendar** — Completed, upcoming, and next race indicators
- **Countdown Timer** — Live countdown to next race
- **Podium Results** — Last race top 3
- **News Feed** — Latest F1 updates
- **Auto-refresh** — Data updates every 60 seconds

## Quick Deploy (5 minutes)

### Option 1: Automated Script (Recommended)

```powershell
cd C:\Users\Megh\f1-pit-wall
.\deploy-to-github.ps1
```

Follow the prompts, then enable GitHub Pages in Settings.

### Option 2: Manual

```powershell
cd C:\Users\Megh\f1-pit-wall
git init
git checkout -b main
git add .
git commit -m "F1 Pit Wall initial commit"
git remote add origin https://github.com/YOUR_USERNAME/f1-pit-wall.git
git push -u origin main
```

Then: **GitHub Repo → Settings → Pages → Deploy from main branch**

## How It Works

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  GitHub Pages   │────▶│  index.html  │────▶│  Jolpi.ca   │
│  (Static Host)  │     │  (Dashboard) │     │  (F1 Data)  │
└─────────────────┘     └──────────────┘     └─────────────┘
                              │
                              ▼
                       ┌─────────────┐
                       │  Browser    │
                       │  (Renders)  │
                       └─────────────┘
```

**No Python. No server. No costs.** Just pure client-side JavaScript fetching F1 data.

## Data Sources

| Data Type | Source |
|-----------|--------|
| Standings | Jolpi.ca (Ergast mirror) |
| Schedule | Jolpi.ca API |
| Results | Jolpi.ca API |
| Team Colors | Hardcoded (official F1) |

## Customization

### Change Favorite Driver

In `index.html`, search for `FAV_DRIVER` and update:

```javascript
const FAV_DRIVER = 'norris';  // Change to 'verstappen', 'leclerc', etc.
```

### Change Favorite Team

```javascript
const FAV_TEAM = 'mclaren';  // Change to 'ferrari', 'mercedes', etc.
```

### Update Team Colors

Search for `getTeamColor()` in the script and modify:

```javascript
const colors = {
    'mercedes': '#27F4D2',
    'ferrari': '#E8002D',
    'mclaren': '#FF8000',
    // ...
};
```

## Project Structure

```
f1-pit-wall/
├── index.html              # Main dashboard (deploy this!)
├── README.md               # This file
├── DEPLOYMENT.md           # Detailed deployment guide
├── deploy-to-github.ps1    # Automated deploy script
├── app.py                  # (Optional) Local Flask server
└── requirements.txt        # (Optional) Python dependencies
```

## Hosting Options

| Platform | Free | 24/7 | Notes |
|----------|------|------|-------|
| GitHub Pages | ✅ | ✅ | Recommended |
| Vercel | ✅ | ✅ | Faster CDN |
| Netlify | ✅ | ✅ | Drag & drop |
| Render | ✅ | ⚠️ | Sleeps on free tier |
| Local | ✅ | ❌ | Need `python app.py` |

## Troubleshooting

**Site shows 404**
- Wait 2-3 minutes for GitHub Pages build
- Check Settings → Pages → Branch is set to `main`

**Data not loading**
- Open browser DevTools (F12) → Console
- Check for CORS or network errors
- Jolpi.ca API may be temporarily rate-limited

**Want to update the site?**
```powershell
git add index.html
git commit -m "Updated dashboard"
git push
```

## Credits

- UI Design: Custom F1-inspired theme
- Data: [Jolpi.ca Ergast Mirror](https://api.jolpi.ca/)
- Fonts: Playfair Display, Inter, JetBrains Mono (Google Fonts)

## License

Personal use only. F1 data subject to API terms.

---

**Come on Lando!** 🧡
